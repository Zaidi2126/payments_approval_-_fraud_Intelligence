"""
Seed demo data: payout requests + risk decisions + human reviews.

Ensures all 5 fraud patterns appear at least once per day. Then runs
recompute_daily_metrics and recompute_calibration_stats.

Usage:
  python manage.py seed_demo_data
  python manage.py seed_demo_data --days 3 --per_day 50 --reviews 0.2
"""

import random
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils import timezone

from risk_engine.models import PayoutRequest, RiskDecision, HumanReview
from risk_engine.engine import run_engine, EngineInput
from risk_engine.fraud_readiness import TOP_5_PATTERNS, build_scenario_input

SEED = 42
REVIEWERS = ["reviewer_1", "reviewer_2", "reviewer_3"]
REVIEW_FLIP_PROBABILITY = 0.10  # 10% chance human flips vs system
MIN_PER_PATTERN_PER_DAY = 2  # at least this many of each pattern per day


def _base_input_for_day(day_index: int, request_index: int) -> EngineInput:
    """Deterministic base payload for variety but reproducible."""
    r = random.Random(SEED + day_index * 1000 + request_index)
    amount = Decimal(str(round(r.uniform(50, 500), 2)))
    return EngineInput(
        user_id=f"demo_user_{day_index}_{request_index}",
        amount=amount,
        currency="USD",
        payment_method_id=f"pm_demo_{request_index}",
        payment_method_age_days=r.randint(0, 90),
        country="US",
        ip_address="192.168.1.1",
        vpn_detected=False,
        total_trades=r.randint(0, 50),
        total_trade_volume=amount * Decimal(str(round(r.uniform(0.5, 2.0), 2))),
        withdrawals_last_1h=r.randint(0, 2) if r.random() > 0.7 else 0,
        withdrawals_last_24h=r.randint(0, 5) if r.random() > 0.8 else None,
        deposits_last_1h=None,
        expected_country="US",
    )


def _create_payout_and_decision(engine_input: EngineInput, created_at) -> RiskDecision:
    """Create PayoutRequest and RiskDecision from engine run; set created_at."""
    result = run_engine(engine_input)
    payout = PayoutRequest(
        user_id=engine_input.user_id,
        amount=engine_input.amount,
        currency=engine_input.currency,
        payment_method_id=engine_input.payment_method_id,
        payment_method_age_days=engine_input.payment_method_age_days,
        country=engine_input.country,
        ip_address=engine_input.ip_address,
        vpn_detected=engine_input.vpn_detected,
        total_trades=engine_input.total_trades,
        total_trade_volume=engine_input.total_trade_volume,
    )
    payout.save()
    payout.created_at = created_at
    payout.save(update_fields=["created_at"])

    risk_decision = RiskDecision(
        payout_request=payout,
        risk_score=result.risk_score,
        decision=result.decision,
        confidence_score=result.confidence_score,
        regret_level=result.regret_level,
        triggered_signals=result.triggered_signals,
        reasons=result.reasons,
        counterfactuals=result.counterfactuals,
    )
    risk_decision.save()
    risk_decision.created_at = created_at
    risk_decision.save(update_fields=["created_at"])
    return risk_decision


class Command(BaseCommand):
    help = "Seed demo data: payouts, decisions, and human reviews; then recompute metrics."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=3,
            help="Number of days of data to create (default 3).",
        )
        parser.add_argument(
            "--per_day",
            type=int,
            default=50,
            help="Payout requests per day (default 50).",
        )
        parser.add_argument(
            "--reviews",
            type=float,
            default=0.2,
            help="Fraction of approve/block decisions to add a human review (default 0.2).",
        )

    def handle(self, *args, **options):
        days = max(1, options["days"])
        per_day = max(1, options["per_day"])
        reviews_ratio = max(0.0, min(1.0, options["reviews"]))
        random.seed(SEED)

        min_pattern = min(MIN_PER_PATTERN_PER_DAY, per_day // 5 or 1)
        pattern_count = min_pattern * 5  # 5 patterns
        random_count = max(0, per_day - pattern_count)

        total_payouts = 0
        total_reviews = 0

        for day in range(days):
            base_date = timezone.now().date() - timedelta(days=day)
            created_at = timezone.make_aware(
                datetime.combine(base_date, time(12, 0, 0))
            )
            index_in_day = 0

            # Ensure each of the 5 patterns triggers at least min_pattern times per day
            for pattern in TOP_5_PATTERNS:
                for k in range(min_pattern):
                    base = _base_input_for_day(day, index_in_day)
                    scenario_input = build_scenario_input(base, pattern)
                    _create_payout_and_decision(scenario_input, created_at)
                    total_payouts += 1
                    index_in_day += 1

            # Fill the rest with random/normal cases
            for i in range(random_count):
                base = _base_input_for_day(day, pattern_count + i)
                _create_payout_and_decision(base, created_at)
                total_payouts += 1

        # Add human reviews for a fraction of approve/block decisions
        decisions_for_review = list(
            RiskDecision.objects.filter(decision__in=["approve", "block"]).order_by(
                "created_at"
            )
        )
        random.shuffle(decisions_for_review)
        n_review = max(0, int(len(decisions_for_review) * reviews_ratio))
        for rd in decisions_for_review[:n_review]:
            reviewer_id = random.choice(REVIEWERS)
            if random.random() < REVIEW_FLIP_PROBABILITY:
                final_decision = "block" if rd.decision == "approve" else "approve"
            else:
                final_decision = rd.decision
            HumanReview.objects.create(
                risk_decision=rd,
                reviewer_id=reviewer_id,
                final_decision=final_decision,
            )
            total_reviews += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Created {total_payouts} payout requests and {total_reviews} human reviews."
            )
        )

        call_command("recompute_daily_metrics")
        call_command("recompute_calibration_stats")
        self.stdout.write(self.style.SUCCESS("Ran recompute_daily_metrics and recompute_calibration_stats."))
