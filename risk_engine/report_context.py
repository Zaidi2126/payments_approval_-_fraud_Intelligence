"""
Build context dict for the LLM daily report from DailyMetrics, CalibrationStats, and RiskDecisions.
"""

from risk_engine.models import DailyMetrics, CalibrationStats, RiskDecision


def get_daily_report_context_for_date(date):
    """
    Build a single context dict for generate_daily_report() for the given date.
    Includes metrics, calibration (if any), and decision breakdown (risk score distribution, etc.).
    """
    metrics = DailyMetrics.objects.filter(date=date).first()
    calibration = CalibrationStats.objects.filter(date=date).first()

    if not metrics:
        return {
            "date": date.isoformat() if hasattr(date, "isoformat") else str(date),
            "total_requests": 0,
            "auto_approved": 0,
            "auto_blocked": 0,
            "sent_to_review": 0,
        }

    context = {
        "date": metrics.date.isoformat(),
        "total_requests": metrics.total_requests,
        "auto_approved": metrics.auto_approved,
        "auto_blocked": metrics.auto_blocked,
        "sent_to_review": metrics.sent_to_review,
    }

    if calibration:
        context["calibration"] = {
            "reviewed_count": calibration.reviewed_count,
            "correct_count": calibration.correct_count,
            "incorrect_count": calibration.incorrect_count,
            "accuracy_percent": calibration.accuracy_percent,
            "avg_confidence_correct": calibration.avg_confidence_correct,
            "avg_confidence_incorrect": calibration.avg_confidence_incorrect,
            "overconfidence_rate": calibration.overconfidence_rate,
            "underconfidence_rate": calibration.underconfidence_rate,
        }

    # Decision-level stats for that day (richer report)
    decisions = RiskDecision.objects.filter(created_at__date=date).values("decision", "risk_score", "confidence_score")
    decision_list = list(decisions)
    if decision_list:
        by_decision = {}
        for d in decision_list:
            by_decision[d["decision"]] = by_decision.get(d["decision"], 0) + 1
        scores = [d["risk_score"] for d in decision_list]
        confidences = [d["confidence_score"] for d in decision_list]
        # Risk score bands: 0-25, 25-50, 50-75, 75-100
        bands = {"0-25": 0, "25-50": 0, "50-75": 0, "75-100": 0}
        for s in scores:
            if s < 25:
                bands["0-25"] += 1
            elif s < 50:
                bands["25-50"] += 1
            elif s < 75:
                bands["50-75"] += 1
            else:
                bands["75-100"] += 1
        context["decisions_breakdown"] = {
            "count_by_decision": by_decision,
            "risk_score_distribution": bands,
            "avg_risk_score": round(sum(scores) / len(scores), 2) if scores else 0,
            "avg_confidence_score": round(sum(confidences) / len(confidences), 2) if confidences else 0,
            "sample_risk_scores": sorted(scores)[:20],  # first 20 for flavour
        }

    return context
