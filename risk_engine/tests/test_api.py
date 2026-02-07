"""
API tests for payout decision, human review, metrics, risk trajectory, fraud readiness.
"""

import pytest
from rest_framework.test import APIClient

from risk_engine.models import PayoutRequest, RiskDecision, HumanReview, FraudReadinessSnapshot


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
        "final_decision": "approve",
    }
    response = client.post("/api/reviews", review_payload, format="json")
    assert response.status_code == 201
    data = response.json()
    assert "human_review_id" in data
    assert data["risk_decision_id"] == risk_decision_id
    assert data["final_decision"] == "approve"
    assert "reviewed_at" in data

    assert HumanReview.objects.filter(id=data["human_review_id"]).exists()
    hr = HumanReview.objects.get(id=data["human_review_id"])
    assert str(hr.risk_decision_id) == risk_decision_id
    assert hr.reviewer_id == "reviewer_1"
    assert hr.final_decision == "approve"


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
