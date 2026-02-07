from django.contrib import admin
from .models import (
    PayoutRequest,
    RiskDecision,
    HumanReview,
    DailyMetrics,
    FraudReadinessSnapshot,
    CalibrationStats,
    EngineConfig,
    SystemScore,
    AccountFlag,
    EmergingPattern,
)


@admin.register(PayoutRequest)
class PayoutRequestAdmin(admin.ModelAdmin):
    list_display = ("id", "user_id", "amount", "currency", "country", "created_at")
    list_filter = ("currency", "country", "vpn_detected")
    search_fields = ("user_id", "payment_method_id", "ip_address")
    readonly_fields = ("id", "created_at")


@admin.register(RiskDecision)
class RiskDecisionAdmin(admin.ModelAdmin):
    list_display = ("id", "payout_request", "risk_score", "decision", "confidence_score", "regret_level", "created_at")
    list_filter = ("decision", "regret_level")
    search_fields = ("payout_request__user_id",)
    readonly_fields = ("id", "created_at")
    raw_id_fields = ("payout_request",)


@admin.register(HumanReview)
class HumanReviewAdmin(admin.ModelAdmin):
    list_display = ("id", "risk_decision", "reviewer_id", "final_decision", "approved_for_learning", "reviewed_at")
    list_filter = ("final_decision", "approved_for_learning")
    search_fields = ("reviewer_id", "note")
    readonly_fields = ("id", "reviewed_at", "system_explanation")
    raw_id_fields = ("risk_decision",)


@admin.register(DailyMetrics)
class DailyMetricsAdmin(admin.ModelAdmin):
    list_display = ("date", "total_requests", "auto_approved", "auto_blocked", "sent_to_review", "accuracy_percent")
    list_filter = ("date",)
    ordering = ("-date",)


@admin.register(FraudReadinessSnapshot)
class FraudReadinessSnapshotAdmin(admin.ModelAdmin):
    list_display = ("id", "simulated_pattern", "simulated_risk_score", "readiness_level", "created_at")
    list_filter = ("readiness_level", "simulated_pattern")
    readonly_fields = ("id", "created_at")


@admin.register(CalibrationStats)
class CalibrationStatsAdmin(admin.ModelAdmin):
    list_display = (
        "date",
        "reviewed_count",
        "correct_count",
        "incorrect_count",
        "accuracy_percent",
        "overconfidence_rate",
        "underconfidence_rate",
    )
    list_filter = ("date",)
    ordering = ("-date",)


@admin.register(EngineConfig)
class EngineConfigAdmin(admin.ModelAdmin):
    list_display = ("key",)
    search_fields = ("key",)


@admin.register(SystemScore)
class SystemScoreAdmin(admin.ModelAdmin):
    list_display = ("id", "score", "updated_at")
    readonly_fields = ("updated_at",)


@admin.register(AccountFlag)
class AccountFlagAdmin(admin.ModelAdmin):
    list_display = ("user_id", "reason", "created_at")
    search_fields = ("user_id",)


@admin.register(EmergingPattern)
class EmergingPatternAdmin(admin.ModelAdmin):
    list_display = ("signal_combo", "case_count", "last_seen")
    search_fields = ("signal_combo",)
