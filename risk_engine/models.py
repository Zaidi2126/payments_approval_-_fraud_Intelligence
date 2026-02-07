import uuid
from django.db import models
from decimal import Decimal


class PayoutRequest(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user_id = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=20, decimal_places=2)
    currency = models.CharField(max_length=3)
    payment_method_id = models.CharField(max_length=255)
    payment_method_age_days = models.IntegerField()
    country = models.CharField(max_length=255)
    ip_address = models.GenericIPAddressField()
    vpn_detected = models.BooleanField(default=False)
    total_trades = models.IntegerField(default=0)
    total_trade_volume = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal("0"))
    # Optional technical fraud signals (for detectors)
    card_decline_count_24h = models.IntegerField(null=True, blank=True, default=None)
    failed_login_count_24h = models.IntegerField(null=True, blank=True, default=None)
    device_id = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"PayoutRequest {self.id} ({self.user_id}, {self.amount} {self.currency})"


class RiskDecision(models.Model):
    class Decision(models.TextChoices):
        APPROVE = "approve", "Approve"
        REVIEW = "review", "Review"
        BLOCK = "block", "Block"

    class RegretLevel(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    payout_request = models.OneToOneField(
        PayoutRequest,
        on_delete=models.CASCADE,
        related_name="risk_decision",
    )
    risk_score = models.IntegerField()  # 0-100
    decision = models.CharField(max_length=10, choices=Decision.choices)
    confidence_score = models.IntegerField()  # 0-100
    regret_level = models.CharField(max_length=10, choices=RegretLevel.choices)
    triggered_signals = models.JSONField(default=list)  # list of strings
    reasons = models.JSONField(default=list)  # list of strings
    counterfactuals = models.JSONField(default=list)  # list of strings
    review_explanation = models.TextField(
        blank=True,
        help_text="LLM-generated: why this was sent for review (filled on first request when decision=review).",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"RiskDecision {self.id} ({self.decision}, score={self.risk_score})"


class HumanReview(models.Model):
    class FinalDecision(models.TextChoices):
        APPROVE = "approve", "Approve"
        BLOCK = "block", "Block"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    risk_decision = models.ForeignKey(
        RiskDecision,
        on_delete=models.CASCADE,
        related_name="human_reviews",
    )
    reviewer_id = models.CharField(max_length=255)
    final_decision = models.CharField(max_length=10, choices=FinalDecision.choices)
    note = models.TextField(blank=True, help_text="Optional note from the reviewer when overturning.")
    reviewed_at = models.DateTimeField(auto_now_add=True)
    system_explanation = models.TextField(
        blank=True,
        help_text="LLM-generated: why the system made its decision (filled on first admin view).",
    )
    approved_for_learning = models.BooleanField(
        default=False,
        help_text="Admin approved this override so signal weights can be tuned from it.",
    )

    class Meta:
        ordering = ["-reviewed_at"]

    def __str__(self):
        return f"HumanReview {self.id} ({self.final_decision} by {self.reviewer_id})"


class DailyMetrics(models.Model):
    date = models.DateField(unique=True)
    total_requests = models.IntegerField(default=0)
    auto_approved = models.IntegerField(default=0)
    auto_blocked = models.IntegerField(default=0)
    sent_to_review = models.IntegerField(default=0)
    accuracy_percent = models.FloatField(default=0.0)
    false_positive_rate = models.FloatField(default=0.0)
    false_negative_rate = models.FloatField(default=0.0)

    class Meta:
        ordering = ["-date"]
        verbose_name_plural = "Daily metrics"

    def __str__(self):
        return f"DailyMetrics {self.date} (requests={self.total_requests})"


class FraudReadinessSnapshot(models.Model):
    class ReadinessLevel(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    simulated_pattern = models.CharField(max_length=64)
    simulated_risk_score = models.IntegerField()
    readiness_level = models.CharField(max_length=10, choices=ReadinessLevel.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"FraudReadinessSnapshot {self.id} ({self.simulated_pattern}, {self.readiness_level})"


class CalibrationStats(models.Model):
    """
    Per-date calibration stats from HumanReview outcomes.
    Only approve/block system decisions are counted for correctness.
    """

    date = models.DateField(unique=True)
    reviewed_count = models.IntegerField(default=0)
    correct_count = models.IntegerField(default=0)
    incorrect_count = models.IntegerField(default=0)
    accuracy_percent = models.FloatField(default=0.0)
    avg_confidence_correct = models.FloatField(default=0.0)
    avg_confidence_incorrect = models.FloatField(default=0.0)
    overconfidence_rate = models.FloatField(
        default=0.0
    )  # % of incorrect where confidence_score >= 80
    underconfidence_rate = models.FloatField(
        default=0.0
    )  # % of correct where confidence_score < 50

    class Meta:
        ordering = ["-date"]
        verbose_name_plural = "Calibration stats"

    def __str__(self):
        return f"CalibrationStats {self.date} (accuracy={self.accuracy_percent}%)"


class EngineConfig(models.Model):
    """
    Key-value store for engine parameters (e.g. signal_weights).
    Enables admin to view and tune weights; engine reads from here when present.
    """

    key = models.CharField(max_length=64, unique=True)
    value = models.JSONField(default=dict)

    class Meta:
        verbose_name_plural = "Engine config"

    def __str__(self):
        return f"EngineConfig {self.key}"


class SystemScore(models.Model):
    """
    Singleton: one row. Tracks how well the system is doing.
    +points when a user accepts a system decision; -points when user conflicts and admin approves for learning.
    """

    score = models.IntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "System scores"

    def __str__(self):
        return f"SystemScore {self.score}"


class AccountFlag(models.Model):
    """User flagged for fraud/incident (e.g. bulk lock). Engine can force review/block for flagged users."""

    user_id = models.CharField(max_length=255, db_index=True)
    reason = models.CharField(max_length=512)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"AccountFlag {self.user_id}"


class EmergingPattern(models.Model):
    """Discovered pattern: recurring signal combo in blocked/reviewed decisions. LLM describes it."""

    signal_combo = models.CharField(max_length=256)  # e.g. "velocity_abuse,geo_vpn_anomaly"
    case_count = models.IntegerField(default=0)
    first_seen = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(auto_now=True)
    description = models.TextField(blank=True)  # LLM-generated

    class Meta:
        ordering = ["-last_seen"]

    def __str__(self):
        return f"EmergingPattern {self.signal_combo} (n={self.case_count})"
