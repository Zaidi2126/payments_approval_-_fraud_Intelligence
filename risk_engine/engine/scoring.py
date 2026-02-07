"""
Risk score computation from triggered signals.

Base score 0; each signal adds fixed points; cap at 100.
"""

SIGNAL_WEIGHTS: dict[str, int] = {
    "no_trade_fraud": 40,
    "short_trade_abuse": 25,
    "new_payment_method_risk": 15,
    "velocity_abuse": 30,
    "geo_vpn_anomaly": 25,
}

MAX_SCORE = 100
MIN_SCORE = 0


def compute_risk_score(triggered_signals: list[str]) -> int:
    """
    Compute risk score from triggered signal names.

    Base 0; add weight per signal; cap at 100.
    Unknown signals are ignored (no points).
    """
    total = 0
    for name in triggered_signals:
        total += SIGNAL_WEIGHTS.get(name, 0)
    return min(max(total, MIN_SCORE), MAX_SCORE)
