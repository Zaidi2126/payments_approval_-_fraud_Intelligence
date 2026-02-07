"""
Decision, regret level, and confidence score.

All pure functions.
"""

from decimal import Decimal

from .scoring import MAX_SCORE
from .types import EngineInput

# Decision thresholds (inclusive ranges)
APPROVE_MAX = 24
REVIEW_MIN = 25
REVIEW_MAX = 59
BLOCK_MIN = 60


def get_decision(risk_score: int) -> str:
    """
    Map risk score to decision: approve (0-24), review (25-59), block (60-100).
    """
    if risk_score <= APPROVE_MAX:
        return "approve"
    if risk_score <= REVIEW_MAX:
        return "review"
    return "block"


# Regret by amount
REGRET_LOW_MAX = Decimal("200")
REGRET_MEDIUM_MAX = Decimal("1000")


def get_regret_level(amount: Decimal) -> str:
    """
    Regret level from payout amount: < 200 low, 200-1000 medium, > 1000 high.
    """
    if amount < REGRET_LOW_MAX:
        return "low"
    if amount <= REGRET_MEDIUM_MAX:
        return "medium"
    return "high"


def get_confidence_score(
    input: EngineInput,
    risk_score: int,
    triggered_signals: list[str],
) -> int:
    """
    Confidence 0-100 from:
    A) Margin from decision thresholds (further => higher confidence)
    B) Number of signals (more signals => higher confidence)
    C) Missing data penalty (expected_country or velocity fields missing => reduce)
    """
    # A) Margin: distance from nearest threshold (0-24, 25-59, 60-100)
    if risk_score <= APPROVE_MAX:
        margin = APPROVE_MAX - risk_score  # 0..24
    elif risk_score <= REVIEW_MAX:
        margin = min(risk_score - REVIEW_MIN, REVIEW_MAX - risk_score)
        margin = max(0, int(margin))
    else:
        margin = min(risk_score - BLOCK_MIN, MAX_SCORE - risk_score)
        margin = max(0, margin)
    margin_score = min(50, margin * 2)  # up to 50 points from margin

    # B) More signals => higher confidence in the outcome
    num_signals = len(triggered_signals)
    signals_bonus = min(30, num_signals * 10)  # up to 30 points

    # C) Missing data penalty
    penalty = 0
    if input.expected_country is None:
        penalty += 10
    if (
        input.withdrawals_last_1h is None
        and input.withdrawals_last_24h is None
        and input.deposits_last_1h is None
    ):
        penalty += 10
    base = margin_score + signals_bonus - penalty
    return max(0, min(100, int(base)))
