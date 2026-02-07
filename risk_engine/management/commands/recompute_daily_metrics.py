"""
Management command to recompute DailyMetrics from PayoutRequest, RiskDecision, HumanReview.

Usage: python manage.py recompute_daily_metrics
"""

from django.core.management.base import BaseCommand

from risk_engine.models import PayoutRequest, RiskDecision, HumanReview, DailyMetrics


class Command(BaseCommand):
    help = "Recompute DailyMetrics per date from PayoutRequest, RiskDecision, and HumanReview data."

    def handle(self, *args, **options):
        # All distinct dates from PayoutRequest.created_at (date part)
        date_list = list(PayoutRequest.objects.dates("created_at", "day", order="ASC"))
        date_set = set(date_list)

        for date in sorted(date_set):
            self._upsert_metrics_for_date(date)
        self.stdout.write(self.style.SUCCESS(f"Recomputed metrics for {len(date_set)} date(s)."))

    def _upsert_metrics_for_date(self, date):
        # PayoutRequests created on this date (by created_at date)
        payout_ids = list(
            PayoutRequest.objects.filter(created_at__date=date).values_list("id", flat=True)
        )
        total_requests = len(payout_ids)
        if total_requests == 0:
            return

        # RiskDecisions for these payouts
        decisions = RiskDecision.objects.filter(payout_request_id__in=payout_ids)
        auto_approved = decisions.filter(decision="approve").count()
        auto_blocked = decisions.filter(decision="block").count()
        sent_to_review = decisions.filter(decision="review").count()

        # Accuracy, FP rate, FN rate: only consider decisions with decision in (approve, block)
        # that have at least one HumanReview. Use latest review per decision.
        decisions_with_review = decisions.filter(decision__in=["approve", "block"])
        correct = 0
        fp_count = 0  # system block, human approve
        fn_count = 0  # system approve, human block
        system_block_count = 0
        system_approve_count = 0

        for rd in decisions_with_review:
            latest_review = rd.human_reviews.order_by("-reviewed_at").first()
            if not latest_review:
                continue
            human = latest_review.final_decision
            system = rd.decision
            if system == human:
                correct += 1
            if system == "block":
                system_block_count += 1
                if human == "approve":
                    fp_count += 1
            if system == "approve":
                system_approve_count += 1
                if human == "block":
                    fn_count += 1

        total_reviewed = correct + fp_count + fn_count
        accuracy_percent = (100.0 * correct / total_reviewed) if total_reviewed > 0 else 0.0
        false_positive_rate = (fp_count / system_block_count) if system_block_count > 0 else 0.0
        false_negative_rate = (fn_count / system_approve_count) if system_approve_count > 0 else 0.0

        DailyMetrics.objects.update_or_create(
            date=date,
            defaults={
                "total_requests": total_requests,
                "auto_approved": auto_approved,
                "auto_blocked": auto_blocked,
                "sent_to_review": sent_to_review,
                "accuracy_percent": round(accuracy_percent, 2),
                "false_positive_rate": round(false_positive_rate, 4),
                "false_negative_rate": round(false_negative_rate, 4),
            },
        )
