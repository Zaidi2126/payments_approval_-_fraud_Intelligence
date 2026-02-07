from django.urls import path

from .views import (
    HealthView,
    PayoutDecisionView,
    PayoutHistoryView,
    HumanReviewCreateView,
    ReviewExplanationView,
    DailyMetricsListView,
    CalibrationStatsListView,
    SendDailyReportView,
    RiskTrajectoryView,
    FraudReadinessSimulateView,
    ConflictedDecisionsListView,
    ConflictedDecisionApproveView,
    AdminWeightsView,
    FraudNetworkView,
    ExposureView,
    BulkIncidentView,
    NaturalLanguageQueryView,
    EmergingPatternsView,
)

urlpatterns = [
    path("health", HealthView.as_view(), name="health"),
    path("api/payouts/decision", PayoutDecisionView.as_view(), name="payout-decision"),
    path("api/payouts/history", PayoutHistoryView.as_view(), name="payout-history"),
    path("api/reports/send-daily-summary", SendDailyReportView.as_view(), name="send-daily-report"),
    path("api/reviews", HumanReviewCreateView.as_view(), name="review-create"),
    path(
        "api/decisions/<uuid:risk_decision_id>/review-explanation",
        ReviewExplanationView.as_view(),
        name="review-explanation",
    ),
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
    path(
        "api/admin/conflicted-decisions",
        ConflictedDecisionsListView.as_view(),
        name="admin-conflicted-decisions",
    ),
    path(
        "api/admin/conflicted-decisions/<uuid:review_id>/approve",
        ConflictedDecisionApproveView.as_view(),
        name="admin-conflicted-approve",
    ),
    path(
        "api/admin/weights",
        AdminWeightsView.as_view(),
        name="admin-weights",
    ),
    path("api/fraud-network", FraudNetworkView.as_view(), name="fraud-network"),
    path("api/exposure", ExposureView.as_view(), name="exposure"),
    path("api/incidents/bulk-action", BulkIncidentView.as_view(), name="bulk-incident"),
    path("api/query", NaturalLanguageQueryView.as_view(), name="nl-query"),
    path("api/patterns/emerging", EmergingPatternsView.as_view(), name="emerging-patterns"),
]
