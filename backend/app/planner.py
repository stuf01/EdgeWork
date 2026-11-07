"""Pure trade-plan calculation helpers (no I/O)."""

from __future__ import annotations

from decimal import Decimal
from math import floor
from typing import Any


def calculate_plan(
    account_size: Decimal,
    risk_percent: Decimal,
    entry: Decimal,
    stop: Decimal,
    target: Decimal,
) -> dict[str, Any]:
    """Calculate a long-side trade plan from account risk and price levels.

    Raises:
        ValueError: If any input fails validation.
    """
    _validate_inputs(account_size, risk_percent, entry, stop, target)

    max_risk_dollars = account_size * risk_percent / Decimal("100")
    risk_per_share = entry - stop
    shares = floor(max_risk_dollars / risk_per_share)
    actual_risk_dollars = Decimal(shares) * risk_per_share
    reward_per_share = target - entry
    potential_profit = Decimal(shares) * reward_per_share
    risk_reward_ratio = reward_per_share / risk_per_share
    position_cost = Decimal(shares) * entry
    exceeds_account = position_cost > account_size

    return {
        "max_risk_dollars": max_risk_dollars,
        "risk_per_share": risk_per_share,
        "shares": shares,
        "actual_risk_dollars": actual_risk_dollars,
        "reward_per_share": reward_per_share,
        "potential_profit": potential_profit,
        "risk_reward_ratio": risk_reward_ratio,
        "position_cost": position_cost,
        "exceeds_account": exceeds_account,
    }


def _validate_inputs(
    account_size: Decimal,
    risk_percent: Decimal,
    entry: Decimal,
    stop: Decimal,
    target: Decimal,
) -> None:
    if account_size <= 0:
        raise ValueError("account_size must be greater than 0")
    if risk_percent <= 0:
        raise ValueError("risk_percent must be greater than 0")
    if risk_percent > Decimal("100"):
        raise ValueError("risk_percent must be less than or equal to 100")
    if entry <= 0:
        raise ValueError("entry must be greater than 0")
    if stop <= 0:
        raise ValueError("stop must be greater than 0")
    if target <= 0:
        raise ValueError("target must be greater than 0")
    if not (stop < entry < target):
        raise ValueError("prices must satisfy stop < entry < target")
