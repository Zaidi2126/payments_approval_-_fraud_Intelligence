"""
Type definitions for the fraud detection engine.

All engine logic is pure: it takes an EngineInput and returns EngineResult.
No database access.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional


@dataclass(frozen=True)
class EngineInput:
    """
    PayoutRequest-like payload plus optional velocity and geo context.

    Velocity fields are not on the PayoutRequest model yet; they are passed
    only at engine evaluation time (e.g. from external source).
    """

    # Core payout fields
    user_id: str
    amount: Decimal
    currency: str
    payment_method_id: str
    payment_method_age_days: int
    country: str
    ip_address: str
    vpn_detected: bool
    total_trades: int
    total_trade_volume: Decimal

    # Optional velocity (not on model yet)
    withdrawals_last_1h: Optional[int] = None
    withdrawals_last_24h: Optional[int] = None
    deposits_last_1h: Optional[int] = None

    # Optional geo context for mismatch check
    expected_country: Optional[str] = None

    # Optional technical fraud signals
    card_decline_count_24h: Optional[int] = None
    failed_login_count_24h: Optional[int] = None
    device_shared_account_count: Optional[int] = None  # how many accounts share this device_id
    account_flagged: bool = False  # user was bulk-flagged (e.g. fraud incident)


@dataclass
class EngineResult:
    """Output of the fraud detection and scoring engine."""

    triggered_signals: list[str]
    risk_score: int  # 0-100
    confidence_score: int  # 0-100
    regret_level: str  # low | medium | high
    decision: str  # approve | review | block
    reasons: list[str]
    counterfactuals: list[str]
