"""
API tests for payout decision, human review, metrics, risk trajectory, fraud readiness.
"""

import pytest
from rest_framework.test import APIClient

from risk_engine.models import (
    PayoutRequest,
    RiskDecision,
    HumanReview,
    FraudReadinessSnapshot,
    CalibrationStats,
    SystemScore,
)


@pytest.mark.django_db
def test_decision_endpoint_creates_rows():
    """POST /api/payouts/decision creates PayoutRequest and RiskDecision and returns decision payload."""
    client = APIClient()
    payload = {
        "user_id": "user_123",
        "amount": 150.50,
        "currency": "USD",
        "payment_method_id": "pm_abc",
        "payment_method_age_days": 10,
        "country": "US",
        "ip_address": "192.168.1.1",
        "vpn_detected": False,
        "total_trades": 5,
        "total_trade_volume": 500.00,
    }
    response = client.post("/api/payouts/decision", payload, format="json")
    assert response.status_code == 200
    data = response.json()
    assert "payout_request_id" in data
    assert "risk_decision_id" in data
    assert data["decision"] in ("approve", "review", "block")
    assert "risk_score" in data
    assert "confidence_score" in data
    assert "regret_level" in data
    assert "triggered_signals" in data
    assert "reasons" in data
    assert "counterfactuals" in data
    assert "created_at" in data

    # DB rows created
    assert PayoutRequest.objects.filter(id=data["payout_request_id"]).exists()
    assert RiskDecision.objects.filter(id=data["risk_decision_id"]).exists()
    rd = RiskDecision.objects.get(id=data["risk_decision_id"])
    assert str(rd.payout_request_id) == data["payout_request_id"]
    assert rd.decision == data["decision"]
    assert rd.risk_score == data["risk_score"]


@pytest.mark.django_db
def test_decision_response_includes_confidence_and_regret_index():
    """POST /api/payouts/decision response includes confidence_and_regret_index with all required fields."""
    client = APIClient()
    payload = {
        "user_id": "idx_user",
        "amount": 100,
        "currency": "USD",
        "payment_method_id": "pm_1",
        "payment_method_age_days": 10,
        "country": "US",
        "ip_address": "192.168.1.1",
        "vpn_detected": False,
        "total_trades": 5,
        "total_trade_volume": 500,
    }
    response = client.post("/api/payouts/decision", payload, format="json")
    assert response.status_code == 200
    data = response.json()
    assert "confidence_and_regret_index" in data
    idx = data["confidence_and_regret_index"]
    assert "confidence_score" in idx
    assert "regret_level" in idx
    assert idx["regret_level"] in ("low", "medium", "high")
    assert "risk_score" in idx
    assert "decision" in idx
    assert "confidence_band" in idx
    assert idx["confidence_band"] in ("low", "medium", "high")
    assert "action_rationale" in idx
    assert isinstance(idx["action_rationale"], str)
    assert "recommended_next_step" in idx
    assert idx["recommended_next_step"] in ("auto_process", "human_review", "block_and_investigate")
    # Mapping: approve -> auto_process, review -> human_review, block -> block_and_investigate
    assert idx["decision"] == data["decision"]
    if data["decision"] == "approve":
        assert idx["recommended_next_step"] == "auto_process"
    elif data["decision"] == "review":
        assert idx["recommended_next_step"] == "human_review"
    else:
        assert idx["recommended_next_step"] == "block_and_investigate"


@pytest.mark.django_db
def test_review_endpoint_creates_human_review():
    """POST /api/reviews creates HumanReview for a given risk_decision_id."""
    # First create a payout and decision
    client = APIClient()
    decision_payload = {
        "user_id": "user_456",
        "amount": 100,
        "currency": "USD",
        "payment_method_id": "pm_xyz",
        "payment_method_age_days": 20,
        "country": "US",
        "ip_address": "10.0.0.1",
        "vpn_detected": False,
        "total_trades": 10,
        "total_trade_volume": 1000,
    }
    dec_resp = client.post("/api/payouts/decision", decision_payload, format="json")
    assert dec_resp.status_code == 200
    risk_decision_id = dec_resp.json()["risk_decision_id"]

    review_payload = {
        "risk_decision_id": risk_decision_id,
        "reviewer_id": "reviewer_1",
        "action": "accept",
    }
    response = client.post("/api/reviews", review_payload, format="json")
    assert response.status_code == 201
    data = response.json()
    assert "human_review_id" in data
    assert data["risk_decision_id"] == risk_decision_id
    assert data["action"] == "accept"
    assert data["final_decision"] == "approve"  # system approved, human accepted
    assert "reviewed_at" in data

    assert HumanReview.objects.filter(id=data["human_review_id"]).exists()
    hr = HumanReview.objects.get(id=data["human_review_id"])
    assert str(hr.risk_decision_id) == risk_decision_id
    assert hr.reviewer_id == "reviewer_1"
    assert hr.final_decision == "approve"


@pytest.mark.django_db
def test_review_conflict_requires_note_and_final_decision():
    """POST /api/reviews with action=conflict requires final_decision and non-empty note."""
    client = APIClient()
    dec = client.post(
        "/api/payouts/decision",
        {
            "user_id": "u1",
            "amount": 50,
            "currency": "USD",
            "payment_method_id": "pm1",
            "payment_method_age_days": 2,
            "country": "US",
            "ip_address": "127.0.0.1",
            "vpn_detected": False,
            "total_trades": 0,
            "total_trade_volume": 0,
        },
        format="json",
    )
    assert dec.status_code == 200
    risk_decision_id = dec.json()["risk_decision_id"]
    system_decision = dec.json()["decision"]

    # conflict without note -> 400
    r1 = client.post(
        "/api/reviews",
        {
            "risk_decision_id": risk_decision_id,
            "reviewer_id": "r1",
            "action": "conflict",
            "final_decision": "block" if system_decision == "approve" else "approve",
        },
        format="json",
    )
    assert r1.status_code == 400
    assert "note" in r1.json()

    # conflict with note -> 201
    other = "block" if system_decision == "approve" else "approve"
    r2 = client.post(
        "/api/reviews",
        {
            "risk_decision_id": risk_decision_id,
            "reviewer_id": "r1",
            "action": "conflict",
            "final_decision": other,
            "note": "Because I am overturning.",
        },
        format="json",
    )
    assert r2.status_code == 201
    assert r2.json()["action"] == "conflict"
    assert r2.json()["final_decision"] == other
    assert "Because I am overturning" in r2.json()["note"]


@pytest.mark.django_db
def test_review_explanation_and_resolve():
    """GET review-explanation for decision=review; POST resolve with final_decision."""
    from decimal import Decimal
    client = APIClient()
    pr = PayoutRequest.objects.create(
        user_id="u_review",
        amount=Decimal("100"),
        currency="USD",
        payment_method_id="pm1",
        payment_method_age_days=5,
        country="US",
        ip_address="127.0.0.1",
        vpn_detected=False,
        total_trades=2,
        total_trade_volume=Decimal("50"),
    )
    rd = RiskDecision.objects.create(
        payout_request=pr,
        risk_score=40,
        decision="review",
        confidence_score=50,
        regret_level="low",
        triggered_signals=["new_payment_method_risk"],
        reasons=[],
        counterfactuals=[],
    )
    # GET review-explanation (will generate and cache)
    r1 = client.get(f"/api/decisions/{rd.id}/review-explanation")
    assert r1.status_code == 200
    assert "explanation" in r1.json()
    assert len(r1.json()["explanation"]) > 0
    rd.refresh_from_db()
    assert rd.review_explanation

    # POST resolve: human picks approve
    r2 = client.post(
        "/api/reviews",
        {"risk_decision_id": str(rd.id), "action": "resolve", "final_decision": "approve"},
        format="json",
    )
    assert r2.status_code == 201
    assert r2.json()["action"] == "resolve"
    assert r2.json()["final_decision"] == "approve"
    assert HumanReview.objects.filter(risk_decision=rd).count() == 1


@pytest.mark.django_db
def test_system_score_increases_on_accept():
    """Accepting a system decision increases system score."""
    client = APIClient()
    dec = client.post(
        "/api/payouts/decision",
        {
            "user_id": "u1",
            "amount": 100,
            "currency": "USD",
            "payment_method_id": "pm1",
            "payment_method_age_days": 20,
            "country": "US",
            "ip_address": "127.0.0.1",
            "vpn_detected": False,
            "total_trades": 10,
            "total_trade_volume": 1000,
        },
        format="json",
    )
    assert dec.status_code == 200
    risk_decision_id = dec.json()["risk_decision_id"]
    before = SystemScore.objects.filter(pk=1).first()
    before_score = before.score if before else 0
    r = client.post(
        "/api/reviews",
        {"risk_decision_id": risk_decision_id, "action": "accept"},
        format="json",
    )
    assert r.status_code == 201
    after = SystemScore.objects.get(pk=1)
    assert after.score == before_score + 10


@pytest.mark.django_db
def test_risk_trajectory_endpoint():
    """GET /api/users/<user_id>/risk-trajectory returns points, trend, momentum, summary."""
    client = APIClient()
    # Create two decisions for same user to get a trajectory
    for _ in range(2):
        client.post(
            "/api/payouts/decision",
            {
                "user_id": "traj_user",
                "amount": 100,
                "currency": "USD",
                "payment_method_id": "pm_1",
                "payment_method_age_days": 10,
                "country": "US",
                "ip_address": "192.168.1.1",
                "vpn_detected": False,
                "total_trades": 5,
                "total_trade_volume": 500,
            },
            format="json",
        )
    response = client.get("/api/users/traj_user/risk-trajectory?days=7")
    assert response.status_code == 200
    data = response.json()
    assert data["user_id"] == "traj_user"
    assert data["window_days"] == 7
    assert "points" in data
    assert len(data["points"]) >= 2
    for pt in data["points"]:
        assert "ts" in pt
        assert "risk_score" in pt
        assert "decision" in pt
    assert data["trend"] in ("rising", "falling", "flat")
    assert -100 <= data["momentum"] <= 100
    assert "summary" in data and "trend" in data["summary"].lower()

    # No data for unknown user
    empty = client.get("/api/users/nonexistent_user_xyz/risk-trajectory?days=7")
    assert empty.status_code == 200
    assert empty.json()["points"] == []
    assert empty.json()["trend"] == "flat"
    assert empty.json()["momentum"] == 0


@pytest.mark.django_db
def test_fraud_readiness_simulation_creates_snapshots():
    """POST /api/fraud-readiness/simulate runs scenarios and creates FraudReadinessSnapshot rows."""
    initial_count = FraudReadinessSnapshot.objects.count()
    client = APIClient()
    payload = {
        "user_id": "sim_user",
        "amount": 200,
        "currency": "USD",
        "payment_method_id": "pm_sim",
        "payment_method_age_days": 5,
        "country": "US",
        "ip_address": "10.0.0.1",
        "vpn_detected": False,
        "total_trades": 10,
        "total_trade_volume": 1000,
    }
    response = client.post("/api/fraud-readiness/simulate", payload, format="json")
    assert response.status_code == 200
    data = response.json()
    assert data["base_user_id"] == "sim_user"
    assert "results" in data
    assert len(data["results"]) == 5  # all top 5 patterns by default
    for r in data["results"]:
        assert "simulated_pattern" in r
        assert "simulated_risk_score" in r
        assert "readiness_level" in r
        assert r["readiness_level"] in ("low", "medium", "high")
        assert "decision" in r
        assert "triggered_signals" in r
        assert "reasons" in r
    assert FraudReadinessSnapshot.objects.count() == initial_count + 5

    # With specific scenarios
    payload["scenarios"] = ["no_trade_fraud", "geo_vpn_anomaly"]
    resp2 = client.post("/api/fraud-readiness/simulate", payload, format="json")
    assert resp2.status_code == 200
    assert len(resp2.json()["results"]) == 2
    assert FraudReadinessSnapshot.objects.count() == initial_count + 5 + 2


@pytest.mark.django_db
def test_recompute_calibration_stats_command_creates_rows():
    """recompute_calibration_stats command creates/upserts CalibrationStats from HumanReview data."""
    from django.core.management import call_command

    client = APIClient()
    # Create a decision (approve) and a human review (approve) -> correct
    dec = client.post(
        "/api/payouts/decision",
        {
            "user_id": "cal_user",
            "amount": 50,
            "currency": "USD",
            "payment_method_id": "pm_1",
            "payment_method_age_days": 20,
            "country": "US",
            "ip_address": "10.0.0.1",
            "vpn_detected": False,
            "total_trades": 10,
            "total_trade_volume": 500,
        },
        format="json",
    )
    assert dec.status_code == 200
    risk_decision_id = dec.json()["risk_decision_id"]
    rev = client.post(
        "/api/reviews",
        {"risk_decision_id": risk_decision_id, "reviewer_id": "r1", "action": "accept"},
        format="json",
    )
    assert rev.status_code == 201

    initial_count = CalibrationStats.objects.count()
    call_command("recompute_calibration_stats")
    assert CalibrationStats.objects.count() >= initial_count + 1
    latest = CalibrationStats.objects.order_by("-date").first()
    assert latest.reviewed_count >= 1
    assert latest.correct_count >= 1
    assert latest.accuracy_percent >= 0


@pytest.mark.django_db
def test_calibration_endpoint_returns_rows():
    """GET /api/metrics/calibration returns calibration stats ordered by date desc."""
    from django.core.management import call_command

    call_command("recompute_calibration_stats")
    client = APIClient()
    response = client.get("/api/metrics/calibration")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    for row in data:
        assert "date" in row
        assert "reviewed_count" in row
        assert "correct_count" in row
        assert "incorrect_count" in row
        assert "accuracy_percent" in row
        assert "avg_confidence_correct" in row
        assert "avg_confidence_incorrect" in row
        assert "overconfidence_rate" in row
        assert "underconfidence_rate" in row


@pytest.mark.django_db
def test_seed_demo_data_command_runs():
    """seed_demo_data command creates PayoutRequest and RiskDecision rows."""
    from django.core.management import call_command

    initial_payouts = PayoutRequest.objects.count()
    initial_decisions = RiskDecision.objects.count()
    call_command("seed_demo_data", days=1, per_day=5, reviews=0.5)
    assert PayoutRequest.objects.count() >= initial_payouts + 5
    assert RiskDecision.objects.count() >= initial_decisions + 5


@pytest.mark.django_db
def test_payout_history_endpoint_returns_rows():
    """GET /api/payouts/history returns rows with decision and human override fields."""
    client = APIClient()
    # Create 3 decisions; add 1 human review that overrides one of them
    dec1 = client.post(
        "/api/payouts/decision",
        {
            "user_id": "hist_user",
            "amount": 100,
            "currency": "USD",
            "payment_method_id": "pm_1",
            "payment_method_age_days": 20,
            "country": "US",
            "ip_address": "10.0.0.1",
            "vpn_detected": False,
            "total_trades": 10,
            "total_trade_volume": 500,
        },
        format="json",
    )
    assert dec1.status_code == 200
    risk_decision_id_1 = dec1.json()["risk_decision_id"]
    client.post(
        "/api/payouts/decision",
        {
            "user_id": "hist_user",
            "amount": 200,
            "currency": "USD",
            "payment_method_id": "pm_2",
            "payment_method_age_days": 20,
            "country": "US",
            "ip_address": "10.0.0.1",
            "vpn_detected": False,
            "total_trades": 10,
            "total_trade_volume": 1000,
        },
        format="json",
    )
    client.post(
        "/api/payouts/decision",
        {
            "user_id": "other_user",
            "amount": 50,
            "currency": "USD",
            "payment_method_id": "pm_3",
            "payment_method_age_days": 20,
            "country": "US",
            "ip_address": "10.0.0.1",
            "vpn_detected": False,
            "total_trades": 10,
            "total_trade_volume": 200,
        },
        format="json",
    )
    # Add human review that overrides (system approved, human conflicts to block)
    rev = client.post(
        "/api/reviews",
        {
            "risk_decision_id": risk_decision_id_1,
            "reviewer_id": "r1",
            "action": "conflict",
            "final_decision": "block",
            "note": "Override: suspicious pattern.",
        },
        format="json",
    )
    assert rev.status_code == 201

    response = client.get("/api/payouts/history?days=7&limit=10")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 3
    for row in data:
        assert "payout_request_id" in row
        assert "risk_decision_id" in row
        assert "created_at" in row
        assert "user_id" in row
        assert "amount" in row
        assert "currency" in row
        assert "decision" in row
        assert "risk_score" in row
        assert "confidence_score" in row
        assert "regret_level" in row
        assert "triggered_signals" in row
        assert "reasons" in row
        assert "counterfactuals" in row
        assert "human_final_decision" in row
        assert "human_reviewed_at" in row
        assert "human_overrode" in row
    # Find the row that got the human review (override)
    overridden = [r for r in data if r["human_final_decision"] == "block" and r["human_overrode"]]
    assert len(overridden) >= 1


@pytest.mark.django_db
def test_send_daily_slack_summary_command_without_webhook():
    """send_daily_slack_summary exits cleanly when SLACK_WEBHOOK_URL is not set."""
    from django.core.management import call_command
    from io import StringIO

    out = StringIO()
    # Ensure webhook is not set (e.g. in test env it might be unset)
    import os
    orig = os.environ.pop("SLACK_WEBHOOK_URL", None)
    try:
        call_command("send_daily_slack_summary", stdout=out)
        out.seek(0)
        text = out.read()
        assert "SLACK_WEBHOOK_URL" in text or "not set" in text.lower()
    finally:
        if orig is not None:
            os.environ["SLACK_WEBHOOK_URL"] = orig
