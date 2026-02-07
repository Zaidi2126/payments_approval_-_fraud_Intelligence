"""
Fraud readiness simulation: build EngineInput overrides to force each pattern to trigger.

Used by POST /api/fraud-readiness/simulate. No DB access here; callers persist snapshots.
"""

from decimal import Decimal
from .engine.types import EngineInput

# Original top 5 + new technical/incident patterns for the decision simulator
TOP_5_PATTERNS = [
    "no_trade_fraud",
    "short_trade_abuse",
    "new_payment_method_risk",
    "velocity_abuse",
    "geo_vpn_anomaly",
]

ALL_SIMULATOR_PATTERNS = TOP_5_PATTERNS + [
    "card_decline_risk",
    "failed_login_risk",
    "device_shared_risk",
    "account_flagged_risk",
]


def _to_input_dict(inp: EngineInput) -> dict:
    """Convert EngineInput to a mutable dict for overrides."""
    return {
        "user_id": inp.user_id,
        "amount": inp.amount,
        "currency": inp.currency,
        "payment_method_id": inp.payment_method_id,
        "payment_method_age_days": inp.payment_method_age_days,
        "country": inp.country,
        "ip_address": inp.ip_address,
        "vpn_detected": inp.vpn_detected,
        "total_trades": inp.total_trades,
        "total_trade_volume": inp.total_trade_volume,
        "withdrawals_last_1h": inp.withdrawals_last_1h,
        "withdrawals_last_24h": inp.withdrawals_last_24h,
        "deposits_last_1h": inp.deposits_last_1h,
        "expected_country": inp.expected_country,
        "card_decline_count_24h": inp.card_decline_count_24h,
        "failed_login_count_24h": inp.failed_login_count_24h,
        "device_shared_account_count": inp.device_shared_account_count,
        "account_flagged": inp.account_flagged,
    }


def build_scenario_input(base: EngineInput, pattern: str) -> EngineInput:
    """
    Return an EngineInput that forces the given pattern to trigger.
    """
    d = _to_input_dict(base)
    if pattern == "no_trade_fraud":
        d["total_trades"] = 0
        d["total_trade_volume"] = Decimal("0")
        d["payment_method_age_days"] = 0
    elif pattern == "short_trade_abuse":
        d["total_trades"] = 1
        d["total_trade_volume"] = Decimal("0")  # very low relative to amount
    elif pattern == "new_payment_method_risk":
        d["payment_method_age_days"] = 0
    elif pattern == "velocity_abuse":
        d["withdrawals_last_1h"] = 5
        d["withdrawals_last_24h"] = 12
        d["deposits_last_1h"] = 6
    elif pattern == "geo_vpn_anomaly":
        d["vpn_detected"] = True
        if d.get("expected_country") is None and d.get("country"):
            d["expected_country"] = "XX"  # force mismatch if no expected_country
    elif pattern == "card_decline_risk":
        d["card_decline_count_24h"] = 3
    elif pattern == "failed_login_risk":
        d["failed_login_count_24h"] = 5
    elif pattern == "device_shared_risk":
        d["device_shared_account_count"] = 4
    elif pattern == "account_flagged_risk":
        d["account_flagged"] = True
    else:
        raise ValueError(f"Unknown pattern: {pattern}")

    return EngineInput(
        user_id=d["user_id"],
        amount=d["amount"],
        currency=d["currency"],
        payment_method_id=d["payment_method_id"],
        payment_method_age_days=d["payment_method_age_days"],
        country=d["country"],
        ip_address=d["ip_address"],
        vpn_detected=d["vpn_detected"],
        total_trades=d["total_trades"],
        total_trade_volume=d["total_trade_volume"],
        withdrawals_last_1h=d.get("withdrawals_last_1h"),
        withdrawals_last_24h=d.get("withdrawals_last_24h"),
        deposits_last_1h=d.get("deposits_last_1h"),
        expected_country=d.get("expected_country"),
        card_decline_count_24h=d.get("card_decline_count_24h"),
        failed_login_count_24h=d.get("failed_login_count_24h"),
        device_shared_account_count=d.get("device_shared_account_count"),
        account_flagged=d.get("account_flagged", False),
    )


def readiness_level_from_score(score: int) -> str:
    """Map risk score to readiness level: low < 25, medium 25-59, high >= 60."""
    if score < 25:
        return "low"
    if score <= 59:
        return "medium"
    return "high"
