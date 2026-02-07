"""
Risk score computation from triggered signals.

Base score 0; each signal adds fixed points; cap at 100.
Weights can be overridden via EngineConfig (key 'signal_weights') for admin tuning.
"""

SIGNAL_WEIGHTS: dict[str, int] = {
    "no_trade_fraud": 40,
    "short_trade_abuse": 25,
    "new_payment_method_risk": 15,
    "velocity_abuse": 30,
    "geo_vpn_anomaly": 25,
    "card_decline_risk": 35,
    "failed_login_risk": 30,
    "device_shared_risk": 40,
    "account_flagged_risk": 100,  # force high score when bulk-flagged
}

MAX_SCORE = 100
MIN_SCORE = 0

CONFIG_KEY_SIGNAL_WEIGHTS = "signal_weights"


def get_signal_weights() -> dict[str, int]:
    """
    Return current signal weights: from EngineConfig if present, else code defaults.
    Lazy import to avoid circular imports.
    """
    try:
        from risk_engine.models import EngineConfig
        out = dict(SIGNAL_WEIGHTS)
        row = EngineConfig.objects.filter(key=CONFIG_KEY_SIGNAL_WEIGHTS).first()
        if row and isinstance(row.value, dict):
            for k, v in row.value.items():
                if isinstance(v, (int, float)):
                    out[k] = int(v)
        return out
    except Exception:
        pass
    return dict(SIGNAL_WEIGHTS)


def compute_risk_score(triggered_signals: list[str], weights: dict[str, int] | None = None) -> int:
    """
    Compute risk score from triggered signal names.

    Base 0; add weight per signal; cap at 100.
    Unknown signals are ignored (no points).
    Uses weights from DB (EngineConfig) when present if weights is None.
    """
    w = weights if weights is not None else get_signal_weights()
    total = 0
    for name in triggered_signals:
        total += w.get(name, 0)
    return min(max(total, MIN_SCORE), MAX_SCORE)
