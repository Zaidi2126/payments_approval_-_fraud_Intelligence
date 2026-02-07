"""
Deterministic fraud detection and scoring engine.

Pure functions only; no DB access, no LLM calls.
"""

from .decisioning import get_decision, get_regret_level, get_confidence_score
from .detectors import run_all_detectors
from .explanations import get_reasons, get_counterfactuals
from .scoring import compute_risk_score
from .types import EngineInput, EngineResult


def run_engine(input: EngineInput) -> EngineResult:
    """
    Given a PayoutRequest-like payload, compute triggered signals, risk score,
    confidence, regret level, decision, reasons, and counterfactuals.

    All logic is pure; no side effects.
    """
    triggered_signals = run_all_detectors(input)
    risk_score = compute_risk_score(triggered_signals)
    decision = get_decision(risk_score)
    regret_level = get_regret_level(input.amount)
    confidence_score = get_confidence_score(input, risk_score, triggered_signals)
    reasons = get_reasons(input, triggered_signals)
    counterfactuals = get_counterfactuals(input, triggered_signals)
    return EngineResult(
        triggered_signals=triggered_signals,
        risk_score=risk_score,
        confidence_score=confidence_score,
        regret_level=regret_level,
        decision=decision,
        reasons=reasons,
        counterfactuals=counterfactuals,
    )

__all__ = [
    "EngineInput",
    "EngineResult",
    "run_engine",
    "run_all_detectors",
    "compute_risk_score",
    "get_decision",
    "get_regret_level",
    "get_confidence_score",
    "get_reasons",
    "get_counterfactuals",
]
