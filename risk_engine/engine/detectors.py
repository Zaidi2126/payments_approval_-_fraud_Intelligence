"""
Deterministic fraud detectors.

Each detector is a pure function: (EngineInput) -> Optional[str].
Returns the signal name if triggered, None otherwise.
"""

from decimal import Decimal

from .types import EngineInput

# Thresholds for no_trade_fraud: "very low" volume and "small" method age
NO_TRADE_MAX_TRADES = 1
NO_TRADE_MAX_VOLUME = Decimal("50")  # very low
NO_TRADE_MAX_PAYMENT_AGE_DAYS = 7


def no_trade_fraud(input: EngineInput) -> str | None:
    """
    Trigger when user has almost no trading history and a new payment method.

    Rule: total_trades <= 1 AND total_trade_volume very low AND payment_method_age_days small.
    """
    if (
        input.total_trades <= NO_TRADE_MAX_TRADES
        and input.total_trade_volume <= NO_TRADE_MAX_VOLUME
        and input.payment_method_age_days <= NO_TRADE_MAX_PAYMENT_AGE_DAYS
    ):
        return "no_trade_fraud"
    return None


# short_trade_abuse: few trades and volume small relative to payout amount
SHORT_TRADE_MAX_TRADES = 3
SHORT_TRADE_VOLUME_RATIO = Decimal("0.5")  # volume must be at least 50% of amount to avoid


def short_trade_abuse(input: EngineInput) -> str | None:
    """
    Trigger when trade history is small and volume is low relative to payout amount.

    Rule: total_trades <= 3 AND trade_volume small relative to amount.
    """
    if input.total_trades <= SHORT_TRADE_MAX_TRADES and input.amount > 0:
        # volume/amount ratio; if volume is less than 50% of amount, consider it abuse
        if input.total_trade_volume < input.amount * SHORT_TRADE_VOLUME_RATIO:
            return "short_trade_abuse"
    return None


# new_payment_method_risk
NEW_PAYMENT_MAX_AGE_DAYS = 3


def new_payment_method_risk(input: EngineInput) -> str | None:
    """
    Trigger when payment method is very new.

    Rule: payment_method_age_days <= 3.
    """
    if input.payment_method_age_days <= NEW_PAYMENT_MAX_AGE_DAYS:
        return "new_payment_method_risk"
    return None


# velocity_abuse
VELOCITY_WITHDRAWALS_1H = 3
VELOCITY_WITHDRAWALS_24H = 10
VELOCITY_DEPOSITS_1H = 5


def velocity_abuse(input: EngineInput) -> str | None:
    """
    Trigger on high withdrawal/deposit velocity.

    Rule: withdrawals_last_1h >= 3 OR withdrawals_last_24h >= 10 OR deposits_last_1h >= 5.
    Missing velocity data is not treated as trigger (caller may apply confidence penalty).
    """
    w1h = input.withdrawals_last_1h if input.withdrawals_last_1h is not None else 0
    w24h = input.withdrawals_last_24h if input.withdrawals_last_24h is not None else 0
    d1h = input.deposits_last_1h if input.deposits_last_1h is not None else 0
    if (
        w1h >= VELOCITY_WITHDRAWALS_1H
        or w24h >= VELOCITY_WITHDRAWALS_24H
        or d1h >= VELOCITY_DEPOSITS_1H
    ):
        return "velocity_abuse"
    return None


def geo_vpn_anomaly(input: EngineInput) -> str | None:
    """
    Trigger on VPN usage or country mismatch.

    Rule: vpn_detected == True OR (expected_country set and country != expected_country).
    """
    if input.vpn_detected:
        return "geo_vpn_anomaly"
    if input.expected_country is not None and input.country != input.expected_country:
        return "geo_vpn_anomaly"
    return None


# All detectors in order
DETECTORS = [
    no_trade_fraud,
    short_trade_abuse,
    new_payment_method_risk,
    velocity_abuse,
    geo_vpn_anomaly,
]


def run_all_detectors(input: EngineInput) -> list[str]:
    """
    Run every detector on the input and return the list of triggered signal names.

    Pure function; no side effects.
    """
    triggered: list[str] = []
    for detector in DETECTORS:
        signal = detector(input)
        if signal is not None and signal not in triggered:
            triggered.append(signal)
    return triggered
