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


class HumanReviewRequestSerializer(serializers.Serializer):
    """Validate input for POST /api/reviews."""

    risk_decision_id = serializers.UUIDField()
    reviewer_id = serializers.CharField(max_length=255)
    final_decision = serializers.ChoiceField(choices=["approve", "block"])


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
    scenarios = serializers.ListField(
        child=serializers.ChoiceField(
            choices=[
                "no_trade_fraud",
                "short_trade_abuse",
                "new_payment_method_risk",
                "velocity_abuse",
                "geo_vpn_anomaly",
            ]
        ),
        required=False,
        allow_null=True,
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
