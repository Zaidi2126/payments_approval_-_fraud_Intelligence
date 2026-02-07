"""
API views for risk_engine: health, payout decision, human review, daily metrics.
"""

from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response

from .models import PayoutRequest, RiskDecision, HumanReview, DailyMetrics
from .serializers import PayoutDecisionRequestSerializer, HumanReviewRequestSerializer
from .engine import run_engine, EngineInput


class HealthView(APIView):
    def get(self, request):
        return Response({"status": "ok"})


class PayoutDecisionView(APIView):
    """
    POST /api/payouts/decision
    Create PayoutRequest, run engine, create RiskDecision, return full decision response.
    """

    def post(self, request):
        ser = PayoutDecisionRequestSerializer(data=request.data)
        if not ser.is_valid():
            return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)
        data = ser.validated_data

        # Create PayoutRequest (DB fields only; optional engine fields not stored on model)
        payout = PayoutRequest.objects.create(
            user_id=data["user_id"],
            amount=data["amount"],
            currency=data["currency"],
            payment_method_id=data["payment_method_id"],
            payment_method_age_days=data["payment_method_age_days"],
            country=data["country"],
            ip_address=data["ip_address"],
            vpn_detected=data["vpn_detected"],
            total_trades=data["total_trades"],
            total_trade_volume=data["total_trade_volume"],
        )

        # Build engine input (include optional fields)
        engine_input = EngineInput(
            user_id=data["user_id"],
            amount=data["amount"],
            currency=data["currency"],
            payment_method_id=data["payment_method_id"],
            payment_method_age_days=data["payment_method_age_days"],
            country=data["country"],
            ip_address=data["ip_address"],
            vpn_detected=data["vpn_detected"],
            total_trades=data["total_trades"],
            total_trade_volume=data["total_trade_volume"],
            expected_country=data.get("expected_country"),
            withdrawals_last_1h=data.get("withdrawals_last_1h"),
            withdrawals_last_24h=data.get("withdrawals_last_24h"),
            deposits_last_1h=data.get("deposits_last_1h"),
        )
        result = run_engine(engine_input)

        # Create RiskDecision linked to PayoutRequest
        risk_decision = RiskDecision.objects.create(
            payout_request=payout,
            risk_score=result.risk_score,
            decision=result.decision,
            confidence_score=result.confidence_score,
            regret_level=result.regret_level,
            triggered_signals=result.triggered_signals,
            reasons=result.reasons,
            counterfactuals=result.counterfactuals,
        )

        response_payload = {
            "payout_request_id": str(payout.id),
            "risk_decision_id": str(risk_decision.id),
            "decision": result.decision,
            "risk_score": result.risk_score,
            "confidence_score": result.confidence_score,
            "regret_level": result.regret_level,
            "triggered_signals": result.triggered_signals,
            "reasons": result.reasons,
            "counterfactuals": result.counterfactuals,
            "created_at": risk_decision.created_at.isoformat(),
        }
        return Response(response_payload, status=status.HTTP_200_OK)


class HumanReviewCreateView(APIView):
    """
    POST /api/reviews
    Create a HumanReview for a given risk_decision_id.
    """

    def post(self, request):
        ser = HumanReviewRequestSerializer(data=request.data)
        if not ser.is_valid():
            return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)
        data = ser.validated_data

        risk_decision_id = data["risk_decision_id"]
        try:
            risk_decision = RiskDecision.objects.get(id=risk_decision_id)
        except RiskDecision.DoesNotExist:
            return Response(
                {"risk_decision_id": ["RiskDecision with this id does not exist."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        review = HumanReview.objects.create(
            risk_decision=risk_decision,
            reviewer_id=data["reviewer_id"],
            final_decision=data["final_decision"],
        )
        return Response(
            {
                "human_review_id": str(review.id),
                "risk_decision_id": str(review.risk_decision_id),
                "final_decision": review.final_decision,
                "reviewed_at": review.reviewed_at.isoformat(),
            },
            status=status.HTTP_201_CREATED,
        )


class DailyMetricsListView(APIView):
    """
    GET /api/metrics/daily
    Return DailyMetrics rows ordered by date descending.
    """

    def get(self, request):
        metrics = DailyMetrics.objects.all().order_by("-date")
        payload = [
            {
                "date": m.date.isoformat(),
                "total_requests": m.total_requests,
                "auto_approved": m.auto_approved,
                "auto_blocked": m.auto_blocked,
                "sent_to_review": m.sent_to_review,
                "accuracy_percent": m.accuracy_percent,
                "false_positive_rate": m.false_positive_rate,
                "false_negative_rate": m.false_negative_rate,
            }
            for m in metrics
        ]
        return Response(payload, status=status.HTTP_200_OK)
