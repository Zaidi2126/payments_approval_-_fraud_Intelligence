"""
Recompute CalibrationStats per date from HumanReview + RiskDecision.

Only approve/block system decisions are scored for correctness.
Usage: python manage.py recompute_calibration_stats
"""

from django.core.management.base import BaseCommand

from risk_engine.models import RiskDecision, HumanReview, CalibrationStats


class Command(BaseCommand):
    help = "Recompute CalibrationStats per date from human review outcomes."

    def handle(self, *args, **options):
        # Distinct dates from RiskDecision (approve/block) that have at least one HumanReview
        date_list = list(
            RiskDecision.objects.filter(
                decision__in=["approve", "block"],
                human_reviews__isnull=False,
            ).dates("created_at", "day")
        )
        date_set = set(date_list)

        for date in sorted(date_set):
            self._upsert_for_date(date)
        self.stdout.write(
            self.style.SUCCESS(f"Recomputed calibration stats for {len(date_set)} date(s).")
        )

    def _upsert_for_date(self, date):
        # RiskDecisions with decision in (approve, block) created on this date
        decisions = RiskDecision.objects.filter(
            created_at__date=date,
            decision__in=["approve", "block"],
        )
        correct_confidence_sum = 0.0
        correct_count = 0
        incorrect_confidence_sum = 0.0
        incorrect_count = 0
        overconfidence_n = 0  # incorrect with confidence >= 80
        underconfidence_n = 0  # correct with confidence < 50

        for rd in decisions:
            latest = rd.human_reviews.order_by("-reviewed_at").first()
            if not latest:
                continue
            human = latest.final_decision
            system = rd.decision
            correct = (system == "approve" and human == "approve") or (
                system == "block" and human == "block"
            )
            conf = rd.confidence_score
            if correct:
                correct_count += 1
                correct_confidence_sum += conf
                if conf < 50:
                    underconfidence_n += 1
            else:
                incorrect_count += 1
                incorrect_confidence_sum += conf
                if conf >= 80:
                    overconfidence_n += 1

        reviewed_count = correct_count + incorrect_count
        if reviewed_count == 0:
            return

        accuracy_percent = round(100.0 * correct_count / reviewed_count, 2)
        avg_correct = round(correct_confidence_sum / correct_count, 2) if correct_count else 0.0
        avg_incorrect = (
            round(incorrect_confidence_sum / incorrect_count, 2) if incorrect_count else 0.0
        )
        overconfidence_rate = (
            round(100.0 * overconfidence_n / incorrect_count, 2) if incorrect_count else 0.0
        )
        underconfidence_rate = (
            round(100.0 * underconfidence_n / correct_count, 2) if correct_count else 0.0
        )

        CalibrationStats.objects.update_or_create(
            date=date,
            defaults={
                "reviewed_count": reviewed_count,
                "correct_count": correct_count,
                "incorrect_count": incorrect_count,
                "accuracy_percent": accuracy_percent,
                "avg_confidence_correct": avg_correct,
                "avg_confidence_incorrect": avg_incorrect,
                "overconfidence_rate": overconfidence_rate,
                "underconfidence_rate": underconfidence_rate,
            },
        )
