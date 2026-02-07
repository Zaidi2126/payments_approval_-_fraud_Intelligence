"""
API views for risk_engine: health, payout decision, human review, daily metrics,
risk trajectory, fraud readiness simulation.
"""

from django.utils import timezone
from datetime import timedelta
from django.db.models import Prefetch

from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response

from .models import (
    PayoutRequest,
    RiskDecision,
    HumanReview,
    DailyMetrics,
    FraudReadinessSnapshot,
    CalibrationStats,
)
from .serializers import (
    PayoutDecisionRequestSerializer,
    HumanReviewRequestSerializer,
    FraudReadinessSimulateSerializer,
    PayoutHistoryRowSerializer,
)
from .engine import run_engine, EngineInput
from .fraud_readiness import (
    TOP_5_PATTERNS,
    build_scenario_input,
    readiness_level_from_score,
)


def _confidence_band(confidence_score: int) -> str:
    """low < 50, medium 50-79, high >= 80."""
    if confidence_score < 50:
        return "low"
    if confidence_score <= 79:
        return "medium"
    return "high"


def _recommended_next_step(decision: str) -> str:
    """approve -> auto_process, review -> human_review, block -> block_and_investigate."""
    return {"approve": "auto_process", "review": "human_review", "block": "block_and_investigate"}[
        decision
    ]


def _action_rationale(risk_score: int, confidence_score: int, triggered_signals: list) -> str:
    """Deterministic sentence referencing risk_score, confidence_score, and signal count."""
    n = len(triggered_signals)
    return (
        f"Risk score {risk_score} with confidence {confidence_score} "
        f"and {n} triggered signal{'s' if n != 1 else ''}."
    )


def build_confidence_and_regret_index(result) -> dict:
    """Build the confidence_and_regret_index object for decision response."""
    return {
        "confidence_score": result.confidence_score,
        "regret_level": result.regret_level,
        "risk_score": result.risk_score,
        "decision": result.decision,
        "confidence_band": _confidence_band(result.confidence_score),
        "action_rationale": _action_rationale(
            result.risk_score, result.confidence_score, result.triggered_signals
        ),
        "recommended_next_step": _recommended_next_step(result.decision),
    }


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
            "confidence_and_regret_index": build_confidence_and_regret_index(result),
        }
        return Response(response_payload, status=status.HTTP_200_OK)


class PayoutHistoryView(APIView):
    """
    GET /api/payouts/history
    Return payout requests with RiskDecision and latest HumanReview (if any).
    Excludes payouts without a RiskDecision.
    """

    def get(self, request):
        try:
            limit = min(200, max(1, int(request.query_params.get("limit", 50))))
        except (TypeError, ValueError):
            limit = 50
        try:
            days = min(365, max(1, int(request.query_params.get("days", 7))))
        except (TypeError, ValueError):
            days = 7
        decision_filter = request.query_params.get("decision")
        user_id_filter = request.query_params.get("user_id")
        since = timezone.now() - timedelta(days=days)

        qs = (
            RiskDecision.objects.filter(created_at__gte=since)
            .select_related("payout_request")
            .prefetch_related(
                Prefetch(
                    "human_reviews",
                    queryset=HumanReview.objects.order_by("-reviewed_at"),
                )
            )
            .order_by("-created_at")
        )
        if decision_filter and decision_filter in ("approve", "review", "block"):
            qs = qs.filter(decision=decision_filter)
        if user_id_filter:
            qs = qs.filter(payout_request__user_id=user_id_filter)

        decisions = list(qs[:limit])
        rows = []
        for rd in decisions:
            payout = rd.payout_request
            latest_review = list(rd.human_reviews.all())[:1]
            latest_review = latest_review[0] if latest_review else None
            human_final_decision = latest_review.final_decision if latest_review else None
            human_reviewed_at = latest_review.reviewed_at if latest_review else None
            human_overrode = bool(
                latest_review and latest_review.final_decision != rd.decision
            )
            rows.append(
                {
                    "payout_request_id": payout.id,
                    "risk_decision_id": rd.id,
                    "created_at": rd.created_at,
                    "user_id": payout.user_id,
                    "amount": payout.amount,
                    "currency": payout.currency,
                    "decision": rd.decision,
                    "risk_score": rd.risk_score,
                    "confidence_score": rd.confidence_score,
                    "regret_level": rd.regret_level,
                    "triggered_signals": rd.triggered_signals,
                    "reasons": rd.reasons,
                    "counterfactuals": rd.counterfactuals,
                    "human_final_decision": human_final_decision,
                    "human_reviewed_at": human_reviewed_at,
                    "human_overrode": human_overrode,
                }
            )
        serializer = PayoutHistoryRowSerializer(rows, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


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


class CalibrationStatsListView(APIView):
    """
    GET /api/metrics/calibration
    Return CalibrationStats rows ordered by date descending.
    """

    def get(self, request):
        stats = CalibrationStats.objects.all().order_by("-date")
        payload = [
            {
                "date": s.date.isoformat(),
                "reviewed_count": s.reviewed_count,
                "correct_count": s.correct_count,
                "incorrect_count": s.incorrect_count,
                "accuracy_percent": s.accuracy_percent,
                "avg_confidence_correct": s.avg_confidence_correct,
                "avg_confidence_incorrect": s.avg_confidence_incorrect,
                "overconfidence_rate": s.overconfidence_rate,
                "underconfidence_rate": s.underconfidence_rate,
            }
            for s in stats
        ]
        return Response(payload, status=status.HTTP_200_OK)


# --- Risk trajectory thresholds ---
TREND_RISING_THRESHOLD = 10
TREND_FALLING_THRESHOLD = -10
MOMENTUM_MIN = -100
MOMENTUM_MAX = 100


class RiskTrajectoryView(APIView):
    """
    GET /api/users/<user_id>/risk-trajectory?days=7
    Return risk points over time plus trend, momentum, and a short summary.
    """

    def get(self, request, user_id):
        try:
            window_days = int(request.query_params.get("days", 7))
        except (TypeError, ValueError):
            window_days = 7
        window_days = max(1, min(window_days, 365))

        since = timezone.now() - timedelta(days=window_days)
        decisions = (
            RiskDecision.objects.filter(payout_request__user_id=user_id)
            .filter(created_at__gte=since)
            .select_related("payout_request")
            .order_by("created_at")
        )
        points = [
            {
                "ts": rd.created_at.isoformat(),
                "risk_score": rd.risk_score,
                "decision": rd.decision,
            }
            for rd in decisions
        ]

        if not points:
            trend = "flat"
            momentum = 0
            summary = f"No risk decisions in the last {window_days} days."
        else:
            first_score = points[0]["risk_score"]
            last_score = points[-1]["risk_score"]
            diff = last_score - first_score
            if diff >= TREND_RISING_THRESHOLD:
                trend = "rising"
            elif diff <= TREND_FALLING_THRESHOLD:
                trend = "falling"
            else:
                trend = "flat"
            momentum = max(MOMENTUM_MIN, min(MOMENTUM_MAX, diff))
            summary = f"Last risk score {last_score}, trend {trend}."

        return Response(
            {
                "user_id": user_id,
                "window_days": window_days,
                "points": points,
                "trend": trend,
                "momentum": momentum,
                "summary": summary,
            },
            status=status.HTTP_200_OK,
        )


class FraudReadinessSimulateView(APIView):
    """
    POST /api/fraud-readiness/simulate
    Simulate top 5 fraud patterns for a hypothetical payout; persist FraudReadinessSnapshot per scenario.
    Does NOT create PayoutRequest or RiskDecision.
    """

    def post(self, request):
        ser = FraudReadinessSimulateSerializer(data=request.data)
        if not ser.is_valid():
            return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)
        data = ser.validated_data

        scenarios = data.get("scenarios") or TOP_5_PATTERNS
        base_input = EngineInput(
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

        results = []
        for pattern in scenarios:
            if pattern not in TOP_5_PATTERNS:
                continue
            scenario_input = build_scenario_input(base_input, pattern)
            result = run_engine(scenario_input)
            level = readiness_level_from_score(result.risk_score)
            FraudReadinessSnapshot.objects.create(
                simulated_pattern=pattern,
                simulated_risk_score=result.risk_score,
                readiness_level=level,
            )
            results.append(
                {
                    "simulated_pattern": pattern,
                    "simulated_risk_score": result.risk_score,
                    "readiness_level": level,
                    "decision": result.decision,
                    "triggered_signals": result.triggered_signals,
                    "reasons": result.reasons,
                }
            )

        return Response(
            {
                "base_user_id": data["user_id"],
                "results": results,
            },
            status=status.HTTP_200_OK,
        )


