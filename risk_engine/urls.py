from django.urls import path

from .views import (
    HealthView,
    PayoutDecisionView,
    HumanReviewCreateView,
    DailyMetricsListView,
)

urlpatterns = [
    path("health", HealthView.as_view(), name="health"),
    path("api/payouts/decision", PayoutDecisionView.as_view(), name="payout-decision"),
    path("api/reviews", HumanReviewCreateView.as_view(), name="review-create"),
    path("api/metrics/daily", DailyMetricsListView.as_view(), name="metrics-daily"),
]
