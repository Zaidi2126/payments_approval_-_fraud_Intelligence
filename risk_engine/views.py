"""
API views for risk_engine: health, payout decision, human review, daily metrics,
risk trajectory, fraud readiness simulation, send daily report.
"""

import os

from django.utils import timezone
from datetime import timedelta
from django.db.models import Prefetch, Sum, Count, Max
from dotenv import load_dotenv

from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response

load_dotenv()

from .models import (
    PayoutRequest,
    RiskDecision,
    HumanReview,
    DailyMetrics,
    FraudReadinessSnapshot,
    CalibrationStats,
    EngineConfig,
    AccountFlag,
    EmergingPattern,
)
from .engine.scoring import (
    SIGNAL_WEIGHTS,
    CONFIG_KEY_SIGNAL_WEIGHTS,
    get_signal_weights,
)
from .llm.client import (
    generate_trajectory_summary,
    generate_daily_report,
    generate_override_explanation,
    generate_review_explanation,
    suggest_weight_adjustment,
    generate_fraud_network_summary,
    generate_exposure_explanation,
    generate_bulk_incident_message,
    interpret_natural_language_query,
    describe_emerging_pattern,
    explain_simulator_rating,
)
from .serializers import (
    PayoutDecisionRequestSerializer,
    HumanReviewRequestSerializer,
    FraudReadinessSimulateSerializer,
    PayoutHistoryRowSerializer,
)
from .engine import run_engine, EngineInput
from .report_context import get_daily_report_context_for_date
from .fraud_readiness import (
    ALL_SIMULATOR_PATTERNS,
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

        # Create PayoutRequest (including optional fraud signals)
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
            card_decline_count_24h=data.get("card_decline_count_24h"),
            failed_login_count_24h=data.get("failed_login_count_24h"),
            device_id=(data.get("device_id") or "").strip(),
        )

        # Compute device_shared_account_count (same device_id across users)
        device_id = (data.get("device_id") or "").strip()
        device_shared_account_count = None
        if device_id:
            from django.db.models import Count
            device_shared_account_count = PayoutRequest.objects.filter(device_id=device_id).values("user_id").distinct().count()

        # Check if user was bulk-flagged (fraud incident)
        account_flagged = AccountFlag.objects.filter(user_id=data["user_id"]).exists()

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
            card_decline_count_24h=data.get("card_decline_count_24h"),
            failed_login_count_24h=data.get("failed_login_count_24h"),
            device_shared_account_count=device_shared_account_count,
            account_flagged=account_flagged,
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
    Create a HumanReview. Human either accepts the system decision or conflicts it.
    - action=accept: agree with system; no note required.
    - action=conflict: overturn; final_decision and note required (note explains why).
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

        action = data["action"]
        system_decision = risk_decision.decision

        if system_decision == "review":
            if action != "resolve":
                return Response(
                    {"action": ["When system decision is 'review', use action 'resolve' with final_decision (approve or block)."]},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            final_decision = data["final_decision"]
            note = (data.get("note") or "").strip()
        elif system_decision in ("approve", "block"):
            if action not in ("accept", "conflict"):
                return Response(
                    {"action": ["When system decision is approve/block, use action 'accept' or 'conflict'."]},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if action == "accept":
                final_decision = risk_decision.decision
                note = ""
            else:
                final_decision = data["final_decision"]
                note = (data.get("note") or "").strip()
                if final_decision == risk_decision.decision:
                    return Response(
                        {"final_decision": ["When conflicting, final_decision must differ from the system decision."]},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
        else:
            return Response(
                {"risk_decision_id": ["Invalid system decision."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        review = HumanReview.objects.create(
            risk_decision=risk_decision,
            reviewer_id=(data.get("reviewer_id") or "").strip() or "",
            final_decision=final_decision,
            note=note,
        )

        # System score: +points when user accepts an approve/block decision
        if system_decision in ("approve", "block") and action == "accept":
            from .models import SystemScore
            obj, _ = SystemScore.objects.get_or_create(pk=1, defaults={"score": 0})
            obj.score += 10
            obj.save(update_fields=["score"])

        return Response(
            {
                "human_review_id": str(review.id),
                "risk_decision_id": str(review.risk_decision_id),
                "action": action,
                "final_decision": review.final_decision,
                "note": review.note or "",
                "reviewed_at": review.reviewed_at.isoformat(),
            },
            status=status.HTTP_201_CREATED,
        )


class ReviewExplanationView(APIView):
    """
    GET /api/decisions/<risk_decision_id>/review-explanation
    For a decision that was sent for review (decision=review), return LLM-generated explanation
    of why it was sent for review. Filled and cached on first request.
    """

    def get(self, request, risk_decision_id):
        try:
            rd = RiskDecision.objects.select_related("payout_request").get(id=risk_decision_id)
        except RiskDecision.DoesNotExist:
            return Response({"error": "RiskDecision not found."}, status=status.HTTP_404_NOT_FOUND)
        if rd.decision != "review":
            return Response(
                {"error": "This decision was not sent for review; explanation only applies to review decisions."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not rd.review_explanation.strip():
            payout = rd.payout_request
            context = {
                "risk_score": rd.risk_score,
                "triggered_signals": rd.triggered_signals or [],
                "reasons": rd.reasons or [],
                "payout_summary": (
                    f"user_id={payout.user_id} amount={payout.amount} {payout.currency} "
                    f"payment_method_age_days={payout.payment_method_age_days} country={payout.country}"
                ),
            }
            rd.review_explanation = generate_review_explanation(context)
            rd.save(update_fields=["review_explanation"])
        return Response(
            {"risk_decision_id": str(rd.id), "explanation": rd.review_explanation},
            status=status.HTTP_200_OK,
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


class SendDailyReportView(APIView):
    """
    POST /api/reports/send-daily-summary
    Sends today's (latest) daily metrics + calibration to Slack.
    Frontend sends slack_webhook_url in the request body; that URL is used for this request only.
    """

    def post(self, request):
        # Webhook from request body (FE provides it); fallback to env for CLI/backward compatibility
        webhook_url = None
        if request.data and isinstance(request.data, dict):
            webhook_url = (request.data.get("slack_webhook_url") or "").strip()
        if not webhook_url:
            webhook_url = (os.getenv("SLACK_WEBHOOK_URL") or "").strip()
        if not webhook_url:
            return Response(
                {
                    "success": False,
                    "error": "slack_webhook_url is required. Send it in the request body: { \"slack_webhook_url\": \"https://hooks.slack.com/...\" }",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        latest = DailyMetrics.objects.order_by("-date").first()
        if not latest:
            return Response(
                {
                    "success": False,
                    "error": "No daily metrics found. Run recompute_daily_metrics or seed_demo_data first.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        calibration = CalibrationStats.objects.filter(date=latest.date).first()
        report = {
            "date": latest.date.isoformat(),
            "total_requests": latest.total_requests,
            "auto_approved": latest.auto_approved,
            "auto_blocked": latest.auto_blocked,
            "sent_to_review": latest.sent_to_review,
        }
        if calibration:
            report["accuracy_percent"] = calibration.accuracy_percent
            report["overconfidence_rate"] = calibration.overconfidence_rate
            report["underconfidence_rate"] = calibration.underconfidence_rate

        context = get_daily_report_context_for_date(latest.date)
        detailed_report = generate_daily_report(context)
        report["detailed_report"] = detailed_report

        slack_fields = [
            {"title": "Date", "value": report["date"], "short": True},
            {"title": "Total requests", "value": str(report["total_requests"]), "short": True},
            {"title": "Auto approved", "value": str(report["auto_approved"]), "short": True},
            {"title": "Auto blocked", "value": str(report["auto_blocked"]), "short": True},
            {"title": "Sent to review", "value": str(report["sent_to_review"]), "short": True},
        ]
        if calibration:
            slack_fields.append({"title": "Accuracy %", "value": f"{calibration.accuracy_percent}", "short": True})
            slack_fields.append({"title": "Overconfidence rate %", "value": f"{calibration.overconfidence_rate}", "short": True})
            slack_fields.append({"title": "Underconfidence rate %", "value": f"{calibration.underconfidence_rate}", "short": True})

        slack_payload = {
            "attachments": [
                {
                    "title": "Daily Payouts Summary",
                    "fields": slack_fields,
                    "text": detailed_report,
                    "color": "#36a64f",
                }
            ]
        }

        try:
            import requests
            resp = requests.post(webhook_url, json=slack_payload, timeout=30)
            resp.raise_for_status()
        except Exception as e:
            return Response(
                {"success": False, "error": f"Failed to send to Slack: {str(e)}", "report": report},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        return Response(
            {
                "success": True,
                "message": "Daily report sent to Slack.",
                "report": report,
            },
            status=status.HTTP_200_OK,
        )


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


# --- Admin: conflicted decisions and signal weights ---


def _ensure_signal_weights_seeded():
    """Create EngineConfig signal_weights from code defaults if missing."""
    if not EngineConfig.objects.filter(key=CONFIG_KEY_SIGNAL_WEIGHTS).exists():
        EngineConfig.objects.create(key=CONFIG_KEY_SIGNAL_WEIGHTS, value=dict(SIGNAL_WEIGHTS))


class ConflictedDecisionsListView(APIView):
    """
    GET /api/admin/conflicted-decisions
    List decisions where the human overturned the system (final_decision != system decision).
    For each, include LLM-generated system explanation (why the system did what it did) and human note.
    """

    def get(self, request):
        # HumanReviews that are overrides: human final_decision != risk_decision.decision
        reviews = (
            HumanReview.objects.filter(
                risk_decision__decision__in=["approve", "block"],
            )
            .select_related("risk_decision", "risk_decision__payout_request")
            .order_by("-reviewed_at")
        )
        overrides = []
        for rev in reviews:
            rd = rev.risk_decision
            if rd.decision == rev.final_decision:
                continue
            payout = rd.payout_request
            payout_summary = (
                f"user_id={payout.user_id} amount={payout.amount} {payout.currency} "
                f"payment_method_age_days={payout.payment_method_age_days} country={payout.country} "
                f"vpn={payout.vpn_detected} total_trades={payout.total_trades}"
            )
            context = {
                "system_decision": rd.decision,
                "human_decision": rev.final_decision,
                "risk_score": rd.risk_score,
                "triggered_signals": rd.triggered_signals or [],
                "reasons": rd.reasons or [],
                "human_note": rev.note or "",
                "payout_summary": payout_summary,
            }
            if not rev.system_explanation.strip():
                rev.system_explanation = generate_override_explanation(context)
                rev.save(update_fields=["system_explanation"])
            overrides.append({
                "human_review_id": str(rev.id),
                "risk_decision_id": str(rd.id),
                "payout_request_id": str(payout.id),
                "reviewed_at": rev.reviewed_at.isoformat(),
                "reviewer_id": rev.reviewer_id,
                "system_decision": rd.decision,
                "human_decision": rev.final_decision,
                "human_note": rev.note or "",
                "system_explanation": rev.system_explanation,
                "risk_score": rd.risk_score,
                "triggered_signals": rd.triggered_signals or [],
                "reasons": rd.reasons or [],
                "approved_for_learning": rev.approved_for_learning,
                "payout_summary": payout_summary,
            })
        return Response({"conflicted_decisions": overrides}, status=status.HTTP_200_OK)


class ConflictedDecisionApproveView(APIView):
    """
    POST /api/admin/conflicted-decisions/<review_id>/approve
    Mark the override as approved for learning and get LLM-suggested signal weight adjustments.
    Returns suggested_weights; admin can then apply them via PATCH /api/admin/weights.
    """

    def post(self, request, review_id):
        try:
            rev = HumanReview.objects.select_related("risk_decision", "risk_decision__payout_request").get(
                id=review_id,
            )
        except HumanReview.DoesNotExist:
            return Response(
                {"error": "HumanReview not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        rd = rev.risk_decision
        if rd.decision == rev.final_decision:
            return Response(
                {"error": "This review is not an override (system and human agree)."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        rev.approved_for_learning = True
        rev.save(update_fields=["approved_for_learning"])

        # System score: admin agreed the system was wrong -> lose points
        from .models import SystemScore
        obj, _ = SystemScore.objects.get_or_create(pk=1, defaults={"score": 0})
        obj.score = max(-1000, obj.score - 15)
        obj.save(update_fields=["score"])

        payout = rd.payout_request
        payout_summary = (
            f"user_id={payout.user_id} amount={payout.amount} {payout.currency} "
            f"payment_method_age_days={payout.payment_method_age_days} country={payout.country} "
            f"vpn={payout.vpn_detected} total_trades={payout.total_trades}"
        )
        context = {
            "system_decision": rd.decision,
            "human_decision": rev.final_decision,
            "risk_score": rd.risk_score,
            "triggered_signals": rd.triggered_signals or [],
            "reasons": rd.reasons or [],
            "human_note": rev.note or "",
            "payout_summary": payout_summary,
        }
        current_weights = get_signal_weights()
        suggested_weights = suggest_weight_adjustment(context, current_weights)
        # Store as pending so FE can show "Apply suggested weights"
        _ensure_signal_weights_seeded()
        EngineConfig.objects.update_or_create(
            key="pending_weight_suggestion",
            defaults={
                "value": {
                    "review_id": str(rev.id),
                    "suggested_weights": suggested_weights,
                    "current_weights": current_weights,
                },
            },
        )
        return Response(
            {
                "approved_for_learning": True,
                "suggested_weights": suggested_weights,
                "current_weights": current_weights,
            },
            status=status.HTTP_200_OK,
        )


class AdminWeightsView(APIView):
    """
    GET /api/admin/weights
    Return current signal weights (and optional pending suggestion from last approved override).
    PATCH /api/admin/weights
    Body: { "signal_weights": { "no_trade_fraud": 40, ... } }. Update and return new weights.
    """

    def get(self, request):
        _ensure_signal_weights_seeded()
        current = get_signal_weights()
        pending = None
        row = EngineConfig.objects.filter(key="pending_weight_suggestion").first()
        if row and isinstance(row.value, dict):
            pending = row.value.get("suggested_weights")
        from .models import SystemScore
        score_obj, _ = SystemScore.objects.get_or_create(pk=1, defaults={"score": 0})
        return Response(
            {
                "signal_weights": current,
                "pending_suggestion": pending,
                "system_score": score_obj.score,
            },
            status=status.HTTP_200_OK,
        )

    def patch(self, request):
        data = request.data or {}
        weights = data.get("signal_weights")
        if not isinstance(weights, dict) or not weights:
            return Response(
                {"error": "Body must include 'signal_weights' object with signal names and integer values."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        _ensure_signal_weights_seeded()
        current = get_signal_weights()
        clean = {k: max(0, min(100, int(v))) for k, v in weights.items() if isinstance(v, (int, float))}
        if not clean:
            return Response(
                {"error": "No valid signal_weights provided."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        merged = {**current, **clean}
        EngineConfig.objects.update_or_create(
            key=CONFIG_KEY_SIGNAL_WEIGHTS,
            defaults={"value": merged},
        )
        return Response(
            {"signal_weights": get_signal_weights()},
            status=status.HTTP_200_OK,
        )


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
            fallback = f"No risk decisions in the last {window_days} days."
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
            fallback = (
                f"Risk trend is {trend} (last score {last_score}). "
                f"Prediction unavailable without AI; review trajectory manually."
            )

        summary = generate_trajectory_summary(
            user_id, window_days, points, trend, momentum, fallback
        )

        # Chat-style messages so the frontend can show the trajectory + LLM summary as a conversation
        user_message = f"Risk trajectory for the last {window_days} days."
        chat = [
            {"role": "user", "content": user_message},
            {"role": "assistant", "content": summary},
        ]

        return Response(
            {
                "user_id": user_id,
                "window_days": window_days,
                "points": points,
                "trend": trend,
                "momentum": momentum,
                "summary": summary,
                "chat": chat,
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
        print("[simulate] POST /api/fraud-readiness/simulate received")
        ser = FraudReadinessSimulateSerializer(data=request.data)
        if not ser.is_valid():
            print("[simulate] Validation failed:", ser.errors)
            return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)
        data = ser.validated_data

        scenarios = data.get("scenarios") or TOP_5_PATTERNS
        print(f"[simulate] scenarios={scenarios!r} (count={len(scenarios)})")
        device_shared_account_count = data.get("device_shared_account_count")
        if device_shared_account_count is None:
            device_id = (data.get("device_id") or "").strip()
            if device_id:
                device_shared_account_count = PayoutRequest.objects.filter(
                    device_id=device_id
                ).values("user_id").distinct().count()
        print(f"[simulate] Building base_input for user_id={data['user_id']!r}")
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
            card_decline_count_24h=data.get("card_decline_count_24h"),
            failed_login_count_24h=data.get("failed_login_count_24h"),
            device_shared_account_count=device_shared_account_count,
            account_flagged=data.get("account_flagged", False),
        )

        results = []
        for i, pattern in enumerate(scenarios):
            if pattern not in ALL_SIMULATOR_PATTERNS:
                print(f"[simulate] Skipping unknown pattern {pattern!r}")
                continue
            print(f"[simulate] Scenario {i+1}/{len(scenarios)}: {pattern!r}")
            scenario_input = build_scenario_input(base_input, pattern)
            result = run_engine(scenario_input)
            print(f"[simulate]   -> risk_score={result.risk_score} decision={result.decision!r} signals={result.triggered_signals!r}")
            level = readiness_level_from_score(result.risk_score)
            FraudReadinessSnapshot.objects.create(
                simulated_pattern=pattern,
                simulated_risk_score=result.risk_score,
                readiness_level=level,
            )
            include_rating_explanation = data.get("include_rating_explanation", False)
            if include_rating_explanation:
                print(f"[simulate]   Calling LLM for rating_explanation...")
                rating_explanation = explain_simulator_rating(
                    pattern,
                    result.risk_score,
                    result.decision,
                    result.triggered_signals,
                    result.reasons,
                )
                print(f"[simulate]   Got rating_explanation ({len(rating_explanation)} chars)")
            else:
                signals_str = ", ".join(result.triggered_signals) if result.triggered_signals else "none"
                reasons_str = " | ".join(result.reasons[:5]) if result.reasons else "N/A"
                rating_explanation = (
                    f"This scenario ({pattern}) received risk score {result.risk_score} and decision '{result.decision}' "
                    f"because it triggered: {signals_str}. {reasons_str}"
                )
                print(f"[simulate]   Using fallback rating_explanation (no LLM)")
            results.append(
                {
                    "simulated_pattern": pattern,
                    "simulated_risk_score": result.risk_score,
                    "readiness_level": level,
                    "decision": result.decision,
                    "triggered_signals": result.triggered_signals,
                    "reasons": result.reasons,
                    "rating_explanation": rating_explanation,
                }
            )

        print(f"[simulate] Returning response with {len(results)} results")
        try:
            resp = Response(
                {
                    "base_user_id": data["user_id"],
                    "results": results,
                },
                status=status.HTTP_200_OK,
            )
            print("[simulate] Response built successfully")
            return resp
        except Exception as e:
            print(f"[simulate] ERROR building/returning response: {type(e).__name__}: {e}")
            raise


# --- Fraud network, exposure, bulk incident, NL query, emerging patterns ---


class FraudNetworkView(APIView):
    """
    GET /api/fraud-network?user_id=X&summary=1
    Build graph of accounts linked by same payment_method_id, ip_address, or device_id.
    If summary=1, include LLM-generated summary.
    """

    def get(self, request):
        user_id = (request.query_params.get("user_id") or "").strip()
        if not user_id:
            return Response({"error": "user_id is required."}, status=status.HTTP_400_BAD_REQUEST)
        include_summary = request.query_params.get("summary", "").lower() in ("1", "true", "yes")

        # Find all payouts for this user to get their payment_method_id, ip_address, device_id
        payouts = PayoutRequest.objects.filter(user_id=user_id).order_by("-created_at")
        if not payouts.exists():
            return Response(
                {"nodes": [{"user_id": user_id, "label": user_id}], "edges": [], "summary": "No links found for this user." if include_summary else None},
                status=status.HTTP_200_OK,
            )
        first = payouts.first()
        pm_id = first.payment_method_id or ""
        ip = str(first.ip_address) if first.ip_address else ""
        device = (first.device_id or "").strip()

        nodes_set = {user_id}
        edges = []
        link_types = []

        if pm_id:
            linked = PayoutRequest.objects.filter(payment_method_id=pm_id).values_list("user_id", flat=True).distinct()
            for uid in linked:
                if uid != user_id:
                    nodes_set.add(uid)
                    edges.append({"from": user_id, "to": uid, "link_type": "payment_method"})
            if linked.count() > 1:
                link_types.append("payment_method")
        if ip:
            linked = PayoutRequest.objects.filter(ip_address=ip).values_list("user_id", flat=True).distinct()
            for uid in linked:
                if uid != user_id:
                    nodes_set.add(uid)
                    edges.append({"from": user_id, "to": uid, "link_type": "ip_address"})
            if linked.count() > 1:
                link_types.append("ip_address")
        if device:
            linked = PayoutRequest.objects.filter(device_id=device).values_list("user_id", flat=True).distinct()
            for uid in linked:
                if uid != user_id:
                    nodes_set.add(uid)
                    edges.append({"from": user_id, "to": uid, "link_type": "device_id"})
            if linked.count() > 1:
                link_types.append("device_id")

        nodes = [{"user_id": u, "label": u} for u in sorted(nodes_set)]
        # Dedupe edges by (from, to, link_type)
        seen = set()
        unique_edges = []
        for e in edges:
            k = (e["from"], e["to"], e["link_type"])
            if k not in seen:
                seen.add(k)
                unique_edges.append(e)

        summary = None
        if include_summary and (nodes or unique_edges):
            summary = generate_fraud_network_summary(nodes, unique_edges, list(set(e["link_type"] for e in unique_edges)))

        return Response(
            {"nodes": nodes, "edges": unique_edges, "summary": summary},
            status=status.HTTP_200_OK,
        )


class ExposureView(APIView):
    """
    GET /api/exposure?user_ids=id1,id2,id3&days=30
    Sum payout amounts for these users in the last N days. Include LLM explanation.
    """

    def get(self, request):
        user_ids_param = (request.query_params.get("user_ids") or "").strip()
        if not user_ids_param:
            return Response({"error": "user_ids is required (comma-separated)."}, status=status.HTTP_400_BAD_REQUEST)
        user_ids = [u.strip() for u in user_ids_param.split(",") if u.strip()]
        if not user_ids:
            return Response({"error": "At least one user_id required."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            days = max(1, min(365, int(request.query_params.get("days", 30))))
        except (TypeError, ValueError):
            days = 30
        since = timezone.now() - timedelta(days=days)
        from django.db.models import Sum
        total = PayoutRequest.objects.filter(user_id__in=user_ids, created_at__gte=since).aggregate(s=Sum("amount"))["s"]
        total_amount = float(total or 0)
        currency = "USD"
        payload = {
            "user_ids": user_ids,
            "total_exposure": total_amount,
            "currency": currency,
            "days": days,
            "user_count": len(user_ids),
        }
        payload["explanation"] = generate_exposure_explanation(total_amount, currency, len(user_ids))
        return Response(payload, status=status.HTTP_200_OK)


class BulkIncidentView(APIView):
    """
    POST /api/incidents/bulk-action
    Body: { "user_ids": ["id1", "id2"], "action": "flag", "reason": "Fraud ring detected." }
    Flags accounts; future payouts for these users get account_flagged_risk.
    Returns drafted client message (LLM) for notifications.
    """

    def post(self, request):
        data = request.data or {}
        user_ids = data.get("user_ids")
        if not isinstance(user_ids, list) or not user_ids:
            return Response({"error": "user_ids (list) is required."}, status=status.HTTP_400_BAD_REQUEST)
        action = (data.get("action") or "flag").strip().lower()
        reason = (data.get("reason") or "Security review").strip()
        for uid in user_ids[:500]:
            AccountFlag.objects.get_or_create(user_id=uid.strip(), defaults={"reason": reason})
        drafted_message = generate_bulk_incident_message(reason, action, len(user_ids))
        return Response(
            {"flagged_count": len(user_ids), "reason": reason, "drafted_client_message": drafted_message},
            status=status.HTTP_200_OK,
        )


class NaturalLanguageQueryView(APIView):
    """
    POST /api/query
    Body: { "question": "Show me accounts that deposited but traded minimally" }
    LLM converts to filters; backend runs query on aggregated payout data and returns matching user_ids.
    """

    def post(self, request):
        question = (request.data.get("question") if request.data else None) or ""
        if not question.strip():
            return Response({"error": "question is required."}, status=status.HTTP_400_BAD_REQUEST)
        schema = (
            "Users have: total_trades (int), total_trade_volume (decimal), payment_method_age_days (int), "
            "vpn_detected (bool), decision (approve|review|block). We aggregate per user from payout requests and risk decisions."
        )
        filters = interpret_natural_language_query(question.strip(), schema)
        if not filters:
            return Response(
                {"question": question, "interpreted_filters": None, "results": [], "message": "Could not interpret question; try rephrasing."},
                status=status.HTTP_200_OK,
            )
        from decimal import Decimal
        qs = PayoutRequest.objects.values("user_id").annotate(
            total_trades_max=Max("total_trades"),
            total_trade_volume_sum=Sum("total_trade_volume"),
            payment_method_age_max=Max("payment_method_age_days"),
            payout_count=Count("id"),
        )
        if filters.get("total_trades_max") is not None:
            qs = qs.filter(total_trades_max__lte=filters["total_trades_max"])
        if filters.get("total_trades_min") is not None:
            qs = qs.filter(total_trades_max__gte=filters["total_trades_min"])
        if filters.get("total_trade_volume_max") is not None:
            qs = qs.filter(total_trade_volume_sum__lte=Decimal(str(filters["total_trade_volume_max"])))
        if filters.get("total_trade_volume_min") is not None:
            qs = qs.filter(total_trade_volume_sum__gte=Decimal(str(filters["total_trade_volume_min"])))
        if filters.get("payment_method_age_max") is not None:
            qs = qs.filter(payment_method_age_max__lte=filters["payment_method_age_max"])
        if filters.get("vpn_detected") is True:
            qs = qs.filter(vpn_detected=True)
        # Get matching users with summary (so we can show why they matched)
        rows = list(qs.values("user_id", "total_trades_max", "total_trade_volume_sum", "payout_count", "payment_method_age_max")[:100])
        # If decision filter, restrict to users who have a RiskDecision with that decision
        if filters.get("decision"):
            dec = filters["decision"].lower()
            if dec in ("approve", "review", "block"):
                rd_user_ids = set(
                    RiskDecision.objects.filter(decision=dec).values_list("payout_request__user_id", flat=True).distinct()
                )
                rows = [r for r in rows if r["user_id"] in rd_user_ids]
        user_ids = [r["user_id"] for r in rows]
        # Fetch recent transactions per user (last 10 payouts each) for display
        recent_by_user = {}
        if user_ids:
            # Last 10 payout requests per user (with decision) for transaction list
            payouts = (
                PayoutRequest.objects.filter(user_id__in=user_ids)
                .select_related("risk_decision")
                .order_by("user_id", "-created_at")
            )
            for pr in payouts:
                uid = pr.user_id
                if uid not in recent_by_user:
                    recent_by_user[uid] = []
                if len(recent_by_user[uid]) < 10:
                    rd = getattr(pr, "risk_decision", None)
                    recent_by_user[uid].append({
                        "payout_request_id": str(pr.id),
                        "amount": float(pr.amount),
                        "currency": pr.currency,
                        "decision": rd.decision if rd else None,
                        "risk_score": rd.risk_score if rd else None,
                        "created_at": pr.created_at.isoformat() if pr.created_at else None,
                    })
        # Build results: account summary + transactions per user
        results = []
        for r in rows:
            uid = r["user_id"]
            results.append({
                "user_id": uid,
                "summary": {
                    "total_trades_max": r.get("total_trades_max"),
                    "total_trade_volume_sum": float(r["total_trade_volume_sum"] or 0),
                    "payout_count": r.get("payout_count"),
                    "payment_method_age_max": r.get("payment_method_age_max"),
                },
                "transactions": recent_by_user.get(uid, []),
            })
        return Response(
            {"question": question, "interpreted_filters": filters, "results": results, "count": len(results)},
            status=status.HTTP_200_OK,
        )


class EmergingPatternsView(APIView):
    """
    GET /api/patterns/emerging
    Discover signal combos from recent block/review decisions (last 7 days); group by combo, count >= 3.
    Return with LLM-generated description per pattern, plus transaction and account IDs for each.
    """

    def get(self, request):
        try:
            days = max(1, min(90, int(request.query_params.get("days", 7))))
        except (TypeError, ValueError):
            days = 7
        refresh_descriptions = request.query_params.get("refresh_descriptions", "").lower() in ("1", "true", "yes")
        since = timezone.now() - timedelta(days=days)
        from collections import defaultdict

        decisions = (
            RiskDecision.objects.filter(
                created_at__gte=since, decision__in=("block", "review")
            )
            .values(
                "id",
                "payout_request_id",
                "payout_request__user_id",
                "triggered_signals",
                "decision",
                "risk_score",
                "created_at",
                "payout_request__amount",
                "payout_request__currency",
                "payout_request__created_at",
            )
        )
        # combo -> { count, cases (list of case detail dicts), account_ids }
        combo_data = defaultdict(lambda: {"count": 0, "cases": [], "account_ids": set()})
        for row in decisions:
            sig_list = row.get("triggered_signals")
            if not sig_list:
                continue
            key = ",".join(sorted(sig_list))
            combo_data[key]["count"] += 1
            pr_id = row.get("payout_request_id")
            user_id = row.get("payout_request__user_id")
            if user_id:
                combo_data[key]["account_ids"].add(user_id)
            created = row.get("created_at")
            pr_created = row.get("payout_request__created_at")
            amount = row.get("payout_request__amount")
            combo_data[key]["cases"].append({
                "payout_request_id": str(pr_id) if pr_id else None,
                "risk_decision_id": str(row.get("id")) if row.get("id") else None,
                "user_id": user_id,
                "amount": float(amount) if amount is not None else 0,
                "currency": row.get("payout_request__currency") or "",
                "decision": row.get("decision"),
                "risk_score": row.get("risk_score"),
                "created_at": (pr_created or created).isoformat() if (pr_created or created) else None,
            })

        patterns = []
        for combo, data in combo_data.items():
            count = data["count"]
            if count < 3:
                continue
            obj, _ = EmergingPattern.objects.update_or_create(
                signal_combo=combo,
                defaults={"case_count": count, "last_seen": timezone.now()},
            )
            if not obj.description or refresh_descriptions:
                obj.description = describe_emerging_pattern(combo, count)
                obj.save(update_fields=["description"])
            elif obj.description:
                print(f"Emerging pattern '{combo}': using cached description (no LLM call)")
            patterns.append({
                "signal_combo": combo,
                "case_count": count,
                "description": obj.description,
                "account_ids": sorted(data["account_ids"]),
                "cases": data["cases"],
            })
        patterns.sort(key=lambda x: -x["case_count"])
        return Response({"patterns": patterns[:20], "days": days}, status=status.HTTP_200_OK)


