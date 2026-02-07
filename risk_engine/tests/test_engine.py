"""
Unit tests for the deterministic fraud detection and scoring engine.
"""

import pytest
from decimal import Decimal

from risk_engine.engine import (
    EngineInput,
    EngineResult,
    run_engine,
    run_all_detectors,
    compute_risk_score,
    get_decision,
    get_regret_level,
    get_confidence_score,
)
from risk_engine.engine.detectors import (
    no_trade_fraud,
    short_trade_abuse,
    new_payment_method_risk,
    velocity_abuse,
    geo_vpn_anomaly,
)


def _base_input(
    *,
    total_trades: int = 10,
    total_trade_volume: Decimal = Decimal("1000"),
    payment_method_age_days: int = 30,
    amount: Decimal = Decimal("100"),
    vpn_detected: bool = False,
    country: str = "US",
    expected_country: str | None = "US",
    withdrawals_last_1h: int | None = 0,
    withdrawals_last_24h: int | None = 0,
    deposits_last_1h: int | None = 0,
) -> EngineInput:
    """Minimal clean input that triggers no signals by default."""
    return EngineInput(
        user_id="user_1",
        amount=amount,
        currency="USD",
        payment_method_id="pm_1",
        payment_method_age_days=payment_method_age_days,
        country=country,
        ip_address="192.168.1.1",
        vpn_detected=vpn_detected,
        total_trades=total_trades,
        total_trade_volume=total_trade_volume,
        withdrawals_last_1h=withdrawals_last_1h,
        withdrawals_last_24h=withdrawals_last_24h,
        deposits_last_1h=deposits_last_1h,
        expected_country=expected_country,
    )


# ----- Clean approve -----


def test_clean_approve_case():
    """No signals => score 0 => approve, low regret for small amount."""
    inp = _base_input(amount=Decimal("100"))
    result = run_engine(inp)
    assert result.triggered_signals == []
    assert result.risk_score == 0
    assert result.decision == "approve"
    assert result.regret_level == "low"
    assert isinstance(result.confidence_score, int)
    assert 0 <= result.confidence_score <= 100
    assert result.reasons == []
    assert result.counterfactuals == []


# ----- Review case -----


def test_review_case():
    """Single moderate signal => score in 25-59 => review."""
    # new_payment_method_risk = +15 would give 15 => approve. So use two signals or one heavy.
    # short_trade_abuse: 3 trades, volume 20, amount 100 => 20 < 50 => +25 => score 25 => review
    inp = _base_input(
        total_trades=3,
        total_trade_volume=Decimal("20"),
        amount=Decimal("100"),
        payment_method_age_days=30,
    )
    result = run_engine(inp)
    assert "short_trade_abuse" in result.triggered_signals
    assert result.risk_score == 25
    assert result.decision == "review"
    assert result.regret_level in ("low", "medium", "high")


# ----- Block case -----


def test_block_case():
    """Enough signals => score >= 60 => block."""
    # no_trade_fraud (40) + geo_vpn_anomaly (25) = 65 => block
    inp = _base_input(
        total_trades=1,
        total_trade_volume=Decimal("10"),
        payment_method_age_days=2,
        vpn_detected=True,
    )
    result = run_engine(inp)
    assert "no_trade_fraud" in result.triggered_signals
    assert "geo_vpn_anomaly" in result.triggered_signals
    assert result.risk_score >= 60
    assert result.decision == "block"


# ----- no_trade_fraud trigger correctness -----


def test_no_trade_trigger_correctness():
    """no_trade_fraud triggers only when trades<=1, volume very low, method age small."""
    # Should trigger
    inp_trigger = _base_input(
        total_trades=1,
        total_trade_volume=Decimal("50"),
        payment_method_age_days=7,
    )
    assert no_trade_fraud(inp_trigger) == "no_trade_fraud"
    signals = run_all_detectors(inp_trigger)
    assert "no_trade_fraud" in signals

    # Should not trigger: too many trades
    inp_ok1 = _base_input(total_trades=2, total_trade_volume=Decimal("0"), payment_method_age_days=1)
    assert no_trade_fraud(inp_ok1) is None

    # Should not trigger: volume too high
    inp_ok2 = _base_input(
        total_trades=1,
        total_trade_volume=Decimal("51"),
        payment_method_age_days=1,
    )
    assert no_trade_fraud(inp_ok2) is None

    # Should not trigger: method too old
    inp_ok3 = _base_input(
        total_trades=1,
        total_trade_volume=Decimal("0"),
        payment_method_age_days=8,
    )
    assert no_trade_fraud(inp_ok3) is None


# ----- VPN / geo_vpn_anomaly trigger correctness -----


def test_vpn_trigger_correctness():
    """geo_vpn_anomaly triggers when vpn_detected or country != expected_country."""
    # VPN detected => trigger
    inp_vpn = _base_input(vpn_detected=True)
    assert geo_vpn_anomaly(inp_vpn) == "geo_vpn_anomaly"
    result = run_engine(inp_vpn)
    assert "geo_vpn_anomaly" in result.triggered_signals
    assert any("VPN" in r for r in result.reasons)

    # Country mismatch => trigger
    inp_mismatch = _base_input(country="XX", expected_country="US")
    assert geo_vpn_anomaly(inp_mismatch) == "geo_vpn_anomaly"

    # No VPN and no expected_country => no trigger (we don't trigger on missing data)
    inp_no_expected = _base_input(vpn_detected=False, expected_country=None)
    assert geo_vpn_anomaly(inp_no_expected) is None

    # Same country => no trigger
    inp_same = _base_input(country="US", expected_country="US", vpn_detected=False)
    assert geo_vpn_anomaly(inp_same) is None


# ----- Scoring and decision helpers -----


def test_compute_risk_score_capped_at_100():
    """Risk score is capped at 100."""
    all_signals = [
        "no_trade_fraud",
        "short_trade_abuse",
        "new_payment_method_risk",
        "velocity_abuse",
        "geo_vpn_anomaly",
    ]
    score = compute_risk_score(all_signals)
    assert score == 100


def test_get_decision_thresholds():
    """Decision thresholds: 0-24 approve, 25-59 review, 60-100 block."""
    assert get_decision(0) == "approve"
    assert get_decision(24) == "approve"
    assert get_decision(25) == "review"
    assert get_decision(59) == "review"
    assert get_decision(60) == "block"
    assert get_decision(100) == "block"


def test_get_regret_level():
    """Regret: amount < 200 low, 200-1000 medium, > 1000 high."""
    assert get_regret_level(Decimal("199")) == "low"
    assert get_regret_level(Decimal("200")) == "medium"
    assert get_regret_level(Decimal("1000")) == "medium"
    assert get_regret_level(Decimal("1001")) == "high"


def test_reasons_and_counterfactuals_per_signal():
    """Reasons and counterfactuals are generated for each triggered signal (LLM or fallback)."""
    inp = _base_input(
        total_trades=1,
        total_trade_volume=Decimal("0"),
        payment_method_age_days=1,
        vpn_detected=True,
    )
    result = run_engine(inp)
    assert len(result.reasons) == len(result.triggered_signals)
    assert len(result.counterfactuals) == len(result.triggered_signals)
    assert "no_trade_fraud" in result.triggered_signals
    assert "geo_vpn_anomaly" in result.triggered_signals


# ----- LLM and fallback explanations (no network) -----


def test_llm_explanations_used_when_mocked(monkeypatch):
    """When generate_explanations is mocked, reasons and counterfactuals come from the mock (no network)."""
    from risk_engine import llm
    mock_reasons = ["LLM-generated reason for signal."]
    mock_counterfactuals = ["LLM-generated counterfactual suggestion."]

    def mock_generate(payload):
        return {"reasons": mock_reasons, "counterfactuals": mock_counterfactuals}

    monkeypatch.setattr(llm.client, "generate_explanations", mock_generate)
    inp = _base_input(total_trades=1, total_trade_volume=Decimal("0"), payment_method_age_days=0)
    result = run_engine(inp)
    assert result.reasons == mock_reasons
    assert result.counterfactuals == mock_counterfactuals
    assert "no_trade_fraud" in result.triggered_signals


def test_fallback_explanations_when_no_api_key(monkeypatch):
    """When OPENAI_API_KEY is missing, fallback reasons and counterfactuals are returned and are non-empty."""
    from risk_engine import llm
    # Force fallback path by making generate_explanations use fallback (no API call)
    from risk_engine.llm.client import _fallback_explanations

    def mock_generate(payload):
        return _fallback_explanations(payload)

    monkeypatch.setattr(llm.client, "generate_explanations", mock_generate)
    inp = _base_input(
        total_trades=1,
        total_trade_volume=Decimal("0"),
        payment_method_age_days=1,
        vpn_detected=True,
    )
    result = run_engine(inp)
    assert len(result.triggered_signals) >= 2
    assert len(result.reasons) == len(result.triggered_signals)
    assert len(result.counterfactuals) == len(result.triggered_signals)
    assert all(isinstance(r, str) and len(r) > 0 for r in result.reasons)
    assert all(isinstance(c, str) and len(c) > 0 for c in result.counterfactuals)
