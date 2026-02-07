"""
API tests for payout decision, human review, and metrics endpoints.
"""

import pytest
from rest_framework.test import APIClient

from risk_engine.models import PayoutRequest, RiskDecision, HumanReview


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
