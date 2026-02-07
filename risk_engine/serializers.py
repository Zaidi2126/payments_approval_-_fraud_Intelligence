"""
DRF serializers for payout decision and human review APIs.
"""

from decimal import Decimal
from rest_framework import serializers


class PayoutDecisionRequestSerializer(serializers.Serializer):
    """Validate input for POST /api/payouts/decision."""

    user_id = serializers.CharField(max_length=255)
    amount = serializers.DecimalField(max_digits=20, decimal_places=2)
    currency = serializers.CharField(max_length=3)
    payment_method_id = serializers.CharField(max_length=255)
    payment_method_age_days = serializers.IntegerField(min_value=0)
    country = serializers.CharField(max_length=255)
    ip_address = serializers.IPAddressField()
    vpn_detected = serializers.BooleanField(default=False)
    total_trades = serializers.IntegerField(min_value=0, default=0)
    total_trade_volume = serializers.DecimalField(
        max_digits=20, decimal_places=2, min_value=Decimal("0"), default=Decimal("0")
    )

    # Optional engine-only fields
    expected_country = serializers.CharField(max_length=255, required=False, allow_null=True)
    withdrawals_last_1h = serializers.IntegerField(min_value=0, required=False, allow_null=True)
    withdrawals_last_24h = serializers.IntegerField(min_value=0, required=False, allow_null=True)
    deposits_last_1h = serializers.IntegerField(min_value=0, required=False, allow_null=True)
    card_decline_count_24h = serializers.IntegerField(min_value=0, required=False, allow_null=True)
    failed_login_count_24h = serializers.IntegerField(min_value=0, required=False, allow_null=True)
    device_id = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")


class HumanReviewRequestSerializer(serializers.Serializer):
    """
    Validate input for POST /api/reviews.
    Human has two options: accept (agree with system) or conflict (overturn).
    When conflicting, final_decision and note are required.
    """

    risk_decision_id = serializers.UUIDField()
    reviewer_id = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    action = serializers.ChoiceField(
        choices=["accept", "conflict", "resolve"],
        help_text="accept = agree; conflict = overturn (note required); resolve = for review, human picks approve/block.",
    )
    final_decision = serializers.ChoiceField(
        choices=["approve", "block"],
        required=False,
        allow_null=True,
        help_text="Required for conflict or resolve. For resolve: human decision. For conflict: must differ from system.",
    )
    note = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        help_text="Required when action is 'conflict'. Optional for resolve.",
    )

    def validate(self, attrs):
        action = attrs.get("action")
        if action == "conflict":
            if attrs.get("final_decision") is None:
                raise serializers.ValidationError(
                    {"final_decision": "Required when action is 'conflict'. Send 'approve' or 'block'."}
                )
            note = (attrs.get("note") or "").strip()
            if not note:
                raise serializers.ValidationError(
                    {"note": "Required when action is 'conflict'. Explain why you are overturning the system decision."}
                )
        if action == "resolve":
            if attrs.get("final_decision") is None:
                raise serializers.ValidationError(
                    {"final_decision": "Required when action is 'resolve'. Send 'approve' or 'block'."}
                )
        return attrs


SIMULATOR_PATTERN_CHOICES = [
    "no_trade_fraud",
    "short_trade_abuse",
    "new_payment_method_risk",
    "velocity_abuse",
    "geo_vpn_anomaly",
    "card_decline_risk",
    "failed_login_risk",
    "device_shared_risk",
    "account_flagged_risk",
]


class FraudReadinessSimulateSerializer(serializers.Serializer):
    """Validate input for POST /api/fraud-readiness/simulate. Base payload + optional scenarios."""

    user_id = serializers.CharField(max_length=255)
    amount = serializers.DecimalField(max_digits=20, decimal_places=2)
    currency = serializers.CharField(max_length=3)
    payment_method_id = serializers.CharField(max_length=255)
    payment_method_age_days = serializers.IntegerField(min_value=0)
    country = serializers.CharField(max_length=255)
    ip_address = serializers.IPAddressField()
    vpn_detected = serializers.BooleanField(default=False)
    total_trades = serializers.IntegerField(min_value=0, default=0)
    total_trade_volume = serializers.DecimalField(
        max_digits=20, decimal_places=2, min_value=Decimal("0"), default=Decimal("0")
    )
    expected_country = serializers.CharField(max_length=255, required=False, allow_null=True)
    withdrawals_last_1h = serializers.IntegerField(min_value=0, required=False, allow_null=True)
    withdrawals_last_24h = serializers.IntegerField(min_value=0, required=False, allow_null=True)
    deposits_last_1h = serializers.IntegerField(min_value=0, required=False, allow_null=True)
    card_decline_count_24h = serializers.IntegerField(min_value=0, required=False, allow_null=True)
    failed_login_count_24h = serializers.IntegerField(min_value=0, required=False, allow_null=True)
    device_id = serializers.CharField(max_length=255, required=False, allow_blank=True, allow_null=True)
    device_shared_account_count = serializers.IntegerField(min_value=0, required=False, allow_null=True)
    account_flagged = serializers.BooleanField(default=False, required=False)
    scenarios = serializers.ListField(
        child=serializers.ChoiceField(choices=SIMULATOR_PATTERN_CHOICES),
        required=False,
        allow_null=True,
    )
    include_rating_explanation = serializers.BooleanField(
        default=False,
        required=False,
        help_text="If true, call LLM for rating_explanation (slower; use longer client timeout). Default false for fast response.",
    )


class PayoutHistoryRowSerializer(serializers.Serializer):
    """Output shape for GET /api/payouts/history rows."""

    payout_request_id = serializers.UUIDField()
    risk_decision_id = serializers.UUIDField()
    created_at = serializers.DateTimeField()
    user_id = serializers.CharField()
    amount = serializers.DecimalField(max_digits=20, decimal_places=2)
    currency = serializers.CharField()
    decision = serializers.CharField()
    risk_score = serializers.IntegerField()
    confidence_score = serializers.IntegerField()
    regret_level = serializers.CharField()
    triggered_signals = serializers.ListField(child=serializers.CharField())
    reasons = serializers.ListField(child=serializers.CharField())
    counterfactuals = serializers.ListField(child=serializers.CharField())
    human_final_decision = serializers.CharField(allow_null=True)
    human_reviewed_at = serializers.DateTimeField(allow_null=True)
    human_overrode = serializers.BooleanField()
