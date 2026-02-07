"""
Seed demo data: payout requests + risk decisions + human reviews.

Use --clear to remove existing payout-related data first.
Creates a curated dataset so you can easily check all decisions, signals, and features.

Usage:
  python manage.py seed_demo_data
  python manage.py seed_demo_data --clear
  python manage.py seed_demo_data --clear --reviews 0.3

After seeding, you can check:
  - Approve (low regret):  user_approve_low (amount 100), user_approve_medium (500)
  - Review:                 user_review_velocity (velocity_abuse), user_review_two_signals (40)
  - Block:                 user_block_multi (no_trade+velocity+geo), user_pattern_* (each pattern)
  - Risk trajectory:       GET .../api/users/traj_user/risk-trajectory?days=7
  - NL query:              POST .../api/query {"question": "accounts that traded minimally"} -> minimal_trader
  - Fraud network:         GET .../api/fraud-network?user_id=network_user_pm_0 (pm_shared_1), network_user_dev_* (dev_shared_1)
  - Emerging patterns:     GET .../api/patterns/emerging?days=7 (geo_vpn, velocity combos)
  - Exposure:             GET .../api/exposure?user_ids=user_approve_low,minimal_trader&days=30
"""

from datetime import datetime, time, timedelta
from decimal import Decimal

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils import timezone

from risk_engine.models import (
    PayoutRequest,
    RiskDecision,
    HumanReview,
    DailyMetrics,
    FraudReadinessSnapshot,
    EmergingPattern,
    AccountFlag,
    CalibrationStats,
)
from risk_engine.engine import run_engine
from risk_engine.engine.types import EngineInput
from risk_engine.fraud_readiness import TOP_5_PATTERNS, build_scenario_input

REVIEWERS = ["reviewer_1", "reviewer_2"]


def _make_ts(days_ago: int):
    """Created_at for today minus days_ago (12:00)."""
    d = timezone.now().date() - timedelta(days=days_ago)
    return timezone.make_aware(datetime.combine(d, time(12, 0, 0)))


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
        card_decline_count_24h=getattr(engine_input, "card_decline_count_24h", None),
        failed_login_count_24h=getattr(engine_input, "failed_login_count_24h", None),
        device_id=getattr(engine_input, "device_id", "") or "",
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


def _base(user_id: str, amount: float, payment_method_id: str = "pm_1", payment_method_age_days: int = 30,
          total_trades: int = 10, total_trade_volume: float = 5000, country: str = "US",
          expected_country: str = "US", vpn: bool = False,
          withdrawals_1h: int | None = 0, withdrawals_24h: int | None = 2, deposits_1h: int | None = 0,
          card_decline: int | None = None, failed_login: int | None = None,
          device_shared: int | None = None, device_id: str = "", account_flagged: bool = False,
          ) -> EngineInput:
    return EngineInput(
        user_id=user_id,
        amount=Decimal(str(amount)),
        currency="USD",
        payment_method_id=payment_method_id,
        payment_method_age_days=payment_method_age_days,
        country=country,
        ip_address="192.168.1.1",
        vpn_detected=vpn,
        total_trades=total_trades,
        total_trade_volume=Decimal(str(total_trade_volume)),
        withdrawals_last_1h=withdrawals_1h,
        withdrawals_last_24h=withdrawals_24h,
        deposits_last_1h=deposits_1h,
        expected_country=expected_country,
        card_decline_count_24h=card_decline,
        failed_login_count_24h=failed_login,
        device_shared_account_count=device_shared,
        account_flagged=account_flagged,
    )


class Command(BaseCommand):
    help = "Seed curated demo data for testing all decisions and features. Use --clear to wipe first."

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Delete existing payouts, decisions, reviews, metrics, snapshots, patterns, flags, calibration.",
        )
        parser.add_argument(
            "--reviews",
            type=float,
            default=0.2,
            help="Fraction of approve/block decisions to add a human review (default 0.2).",
        )

    def handle(self, *args, **options):
        if options["clear"]:
            self._clear()
        self._seed(options.get("reviews", 0.2))

    def _clear(self):
        HumanReview.objects.all().delete()
        RiskDecision.objects.all().delete()
        PayoutRequest.objects.all().delete()
        DailyMetrics.objects.all().delete()
        FraudReadinessSnapshot.objects.all().delete()
        EmergingPattern.objects.all().delete()
        AccountFlag.objects.all().delete()
        CalibrationStats.objects.all().delete()
        self.stdout.write(self.style.WARNING("Cleared payouts, decisions, reviews, metrics, snapshots, patterns, flags, calibration."))

    def _seed(self, reviews_ratio: float):
        created = 0
        # --- 1) Approve: low regret (amount 100), 0 signals ---
        inp = _base("user_approve_low", 100, total_trades=20, total_trade_volume=2000)
        _create_payout_and_decision(inp, _make_ts(0))
        created += 1

        # --- 2) Approve: medium regret (amount 500), 0 signals ---
        inp = _base("user_approve_medium", 500, total_trades=15, total_trade_volume=8000)
        _create_payout_and_decision(inp, _make_ts(0))
        created += 1

        # --- 3) Review: one signal (velocity_abuse = 30) ---
        inp = _base("user_review_velocity", 200, withdrawals_1h=5, withdrawals_24h=12, deposits_1h=6)
        _create_payout_and_decision(inp, _make_ts(1))
        created += 1

        # --- 4) Review: two signals (new_payment_method 15 + short_trade 25 = 40) ---
        inp = _base("user_review_two_signals", 300, payment_method_age_days=0, total_trades=1, total_trade_volume=0)
        _create_payout_and_decision(inp, _make_ts(1))
        created += 1

        # --- 5) Block: multiple signals (no_trade + velocity + geo) ---
        inp = _base("user_block_multi", 1500, total_trades=0, total_trade_volume=0, payment_method_age_days=0,
                   vpn=True, expected_country="XX", withdrawals_1h=5, withdrawals_24h=12, deposits_1h=6)
        _create_payout_and_decision(inp, _make_ts(2))
        created += 1

        # --- 6) One per pattern (for variety and emerging patterns) ---
        for i, pattern in enumerate(TOP_5_PATTERNS):
            base = _base(f"user_pattern_{pattern}", 250 + i * 50, payment_method_age_days=0 if "payment" in pattern else 20,
                        total_trades=0 if "no_trade" in pattern else 1 if "short" in pattern else 10,
                        total_trade_volume=0 if "no_trade" in pattern or "short" in pattern else 3000,
                        withdrawals_1h=5 if pattern == "velocity_abuse" else 0,
                        withdrawals_24h=12 if pattern == "velocity_abuse" else 2,
                        deposits_1h=6 if pattern == "velocity_abuse" else 0,
                        vpn=pattern == "geo_vpn_anomaly", expected_country="XX" if pattern == "geo_vpn_anomaly" else "US")
            inp = build_scenario_input(base, pattern)
            _create_payout_and_decision(inp, _make_ts(i % 3))
            created += 1

        # --- 7) Extra block/review so emerging patterns have 3+ per combo (geo_vpn, velocity) ---
        for i in range(2):
            base = _base(f"user_geo_extra_{i}", 400, vpn=True, expected_country="XX")
            inp = build_scenario_input(base, "geo_vpn_anomaly")
            _create_payout_and_decision(inp, _make_ts(0))
            created += 1
        for i in range(2):
            base = _base(f"user_velocity_extra_{i}", 350, withdrawals_1h=5, withdrawals_24h=12, deposits_1h=6)
            inp = build_scenario_input(base, "velocity_abuse")
            _create_payout_and_decision(inp, _make_ts(0))
            created += 1

        # --- 8) Risk trajectory user: same user_id, 4 payouts ---
        for i in range(4):
            amount = [100, 150, 200, 100][i]
            dec = _base("traj_user", amount, total_trades=5 + i, total_trade_volume=1000 + 500 * i)
            _create_payout_and_decision(dec, _make_ts(i))
            created += 1

        # --- 9) NL query "traded minimally / deposited but traded little": low trades, low volume, approved ---
        inp = _base("minimal_trader", 100, total_trades=1, total_trade_volume=100, payment_method_age_days=5)
        _create_payout_and_decision(inp, _make_ts(0))
        created += 1

        # --- 10) Fraud network: 3 users sharing same payment_method_id ---
        for i in range(3):
            inp = _base(f"network_user_pm_{i}", 200 + i * 100, payment_method_id="pm_shared_1")
            _create_payout_and_decision(inp, _make_ts(i))
            created += 1

        # --- 11) Fraud network: 3 users sharing same device_id (set on PayoutRequest) ---
        for i in range(3):
            inp = _base(f"network_user_dev_{i}", 300, payment_method_id=f"pm_dev_{i}")
            # EngineInput doesn't have device_id field for storage; we set it on PayoutRequest after
            rd = _create_payout_and_decision(inp, _make_ts(i))
            rd.payout_request.device_id = "dev_shared_1"
            rd.payout_request.save(update_fields=["device_id"])
            created += 1

        # --- 12) Human reviews on a subset of approve/block ---
        decisions = list(RiskDecision.objects.filter(decision__in=["approve", "block"]).order_by("created_at"))
        import random
        random.seed(42)
        n_review = max(0, int(len(decisions) * reviews_ratio))
        for rd in random.sample(decisions, min(n_review, len(decisions))):
            HumanReview.objects.create(
                risk_decision=rd,
                reviewer_id=random.choice(REVIEWERS),
                final_decision=rd.decision,
            )

        self.stdout.write(self.style.SUCCESS(f"Created {created} payout requests (+ human reviews)."))
        call_command("recompute_daily_metrics")
        call_command("recompute_calibration_stats")
        self.stdout.write(self.style.SUCCESS("Ran recompute_daily_metrics and recompute_calibration_stats."))
