"""
Explainability: deterministic fallback for reasons and counterfactuals per triggered signal.

Used when OPENAI_API_KEY is missing or the LLM call fails. Default path is LLM (risk_engine.llm.client).
"""

from .detectors import (
    NO_TRADE_MAX_TRADES,
    NO_TRADE_MAX_VOLUME,
    NO_TRADE_MAX_PAYMENT_AGE_DAYS,
    SHORT_TRADE_MAX_TRADES,
    SHORT_TRADE_VOLUME_RATIO,
    NEW_PAYMENT_MAX_AGE_DAYS,
    VELOCITY_WITHDRAWALS_1H,
    VELOCITY_WITHDRAWALS_24H,
    VELOCITY_DEPOSITS_1H,
)
from .types import EngineInput


def get_reasons(input: EngineInput, triggered_signals: list[str]) -> list[str]:
    """
    Build a human-readable reason for each triggered signal (key facts).
    """
    reasons: list[str] = []
    for signal in triggered_signals:
        if signal == "no_trade_fraud":
            reasons.append(
                f"Minimal trading history: total_trades={input.total_trades}, "
                f"total_trade_volume={input.total_trade_volume}, "
                f"payment_method_age_days={input.payment_method_age_days}."
            )
        elif signal == "short_trade_abuse":
            reasons.append(
                f"Trade volume low relative to payout: total_trades={input.total_trades}, "
                f"total_trade_volume={input.total_trade_volume}, amount={input.amount}."
            )
        elif signal == "new_payment_method_risk":
            reasons.append(
                f"New payment method: payment_method_age_days={input.payment_method_age_days} "
                f"(threshold {NEW_PAYMENT_MAX_AGE_DAYS} days)."
            )
        elif signal == "velocity_abuse":
            parts = []
            if input.withdrawals_last_1h is not None and input.withdrawals_last_1h >= VELOCITY_WITHDRAWALS_1H:
                parts.append(f"withdrawals_last_1h={input.withdrawals_last_1h}")
            if input.withdrawals_last_24h is not None and input.withdrawals_last_24h >= VELOCITY_WITHDRAWALS_24H:
                parts.append(f"withdrawals_last_24h={input.withdrawals_last_24h}")
            if input.deposits_last_1h is not None and input.deposits_last_1h >= VELOCITY_DEPOSITS_1H:
                parts.append(f"deposits_last_1h={input.deposits_last_1h}")
            reasons.append("High velocity: " + ", ".join(parts) + ".")
        elif signal == "geo_vpn_anomaly":
            if input.vpn_detected:
                reasons.append("VPN detected; connection may be from unexpected location.")
            elif input.expected_country is not None:
                reasons.append(
                    f"Country mismatch: country={input.country}, expected_country={input.expected_country}."
                )
            else:
                reasons.append("Geo/VPN anomaly triggered.")
        else:
            reasons.append(f"Signal '{signal}' triggered.")
    return reasons


def get_counterfactuals(input: EngineInput, triggered_signals: list[str]) -> list[str]:
    """
    Suggest what would have avoided each trigger (counterfactuals).
    """
    counterfactuals: list[str] = []
    for signal in triggered_signals:
        if signal == "no_trade_fraud":
            counterfactuals.append(
                f"Increase trading activity: more than {NO_TRADE_MAX_TRADES} trade(s), "
                f"total_trade_volume above {NO_TRADE_MAX_VOLUME}, or use a payment method "
                f"older than {NO_TRADE_MAX_PAYMENT_AGE_DAYS} days."
            )
        elif signal == "short_trade_abuse":
            counterfactuals.append(
                f"Increase total trade volume to at least {SHORT_TRADE_VOLUME_RATIO * 100}% of "
                f"payout amount, or have more than {SHORT_TRADE_MAX_TRADES} trades."
            )
        elif signal == "new_payment_method_risk":
            counterfactuals.append(
                f"Use a payment method older than {NEW_PAYMENT_MAX_AGE_DAYS} days."
            )
        elif signal == "velocity_abuse":
            counterfactuals.append(
                f"Reduce withdrawal/deposit velocity: keep withdrawals_last_1h < {VELOCITY_WITHDRAWALS_1H}, "
                f"withdrawals_last_24h < {VELOCITY_WITHDRAWALS_24H}, deposits_last_1h < {VELOCITY_DEPOSITS_1H}."
            )
        elif signal == "geo_vpn_anomaly":
            if input.vpn_detected:
                counterfactuals.append("Disconnect VPN and request from normal connection.")
            else:
                counterfactuals.append(
                    "Request from the expected country or update expected_country if legitimate."
                )
        else:
            counterfactuals.append(f"Address conditions that triggered '{signal}'.")
    return counterfactuals
