from django.urls import path

from .views import (
    HealthView,
    PayoutDecisionView,
    PayoutHistoryView,
    HumanReviewCreateView,
    DailyMetricsListView,
    CalibrationStatsListView,
    SendDailyReportView,
    RiskTrajectoryView,
    FraudReadinessSimulateView,
)

urlpatterns = [
    path("health", HealthView.as_view(), name="health"),
    path("api/payouts/decision", PayoutDecisionView.as_view(), name="payout-decision"),
    path("api/payouts/history", PayoutHistoryView.as_view(), name="payout-history"),
    path("api/reports/send-daily-summary", SendDailyReportView.as_view(), name="send-daily-report"),
    path("api/reviews", HumanReviewCreateView.as_view(), name="review-create"),
    path("api/metrics/daily", DailyMetricsListView.as_view(), name="metrics-daily"),
    path("api/metrics/calibration", CalibrationStatsListView.as_view(), name="metrics-calibration"),
    path(
        "api/users/<str:user_id>/risk-trajectory",
        RiskTrajectoryView.as_view(),
        name="risk-trajectory",
    ),
    path(
        "api/fraud-readiness/simulate",
        FraudReadinessSimulateView.as_view(),
        name="fraud-readiness-simulate",
    ),
]
