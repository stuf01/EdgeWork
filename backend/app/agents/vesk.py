"""VESK — Risk check. Vetoes are final and cannot be overridden."""

from __future__ import annotations

from decimal import Decimal

from app.agents.schemas import VeskCheckInput, VeskInput, VeskOutput, VeskResult
from app.planner import calculate_plan

ZERO = Decimal("0")
TWO = Decimal("2")


def run_vesk(body: VeskInput) -> VeskOutput:
    """Size each candidate and return approve or VETO with every failed reason."""
    return VeskOutput(results=[_check_one(item) for item in body.checks])


def _check_one(item: VeskCheckInput) -> VeskResult:
    reasons: list[str] = []
    shares = 0
    max_loss: Decimal | None = None

    if not item.market_open:
        reasons.append("market_closed")
    if item.within_open_buffer:
        reasons.append("within_open_buffer")
    if item.stop >= item.entry:
        reasons.append("stop_not_below_entry")
    if item.target <= item.entry:
        reasons.append("target_not_above_entry")
    if item.has_open_or_pending:
        reasons.append("existing_open_or_pending")
    if item.open_positions >= item.max_open_positions:
        reasons.append("max_open_positions")
    if item.trades_today >= item.max_trades_per_day:
        reasons.append("max_trades_per_day")

    loss_limit = item.account_size * item.daily_loss_limit_percent / Decimal("100")
    if item.daily_pnl <= -loss_limit:
        reasons.append("daily_loss_limit")

    if item.days_until_earnings is not None and item.days_until_earnings <= 2:
        reasons.append("earnings_within_2_days")

    try:
        plan = calculate_plan(
            item.account_size,
            item.risk_percent,
            item.entry,
            item.stop,
            item.target,
        )
    except ValueError as exc:
        reasons.append(f"planner_invalid:{exc}")
        return VeskResult(
            symbol=item.symbol,
            approved=False,
            shares=0,
            max_loss=None,
            reasons=reasons,
        )

    shares = int(plan["shares"])
    max_loss = plan["actual_risk_dollars"]
    rr = plan["risk_reward_ratio"]
    position_cost = plan["position_cost"]

    if shares <= 0:
        reasons.append("zero_shares")
    if rr < TWO:
        reasons.append("risk_reward_below_2")
    if position_cost > item.buying_power:
        reasons.append("exceeds_buying_power")
    if max_loss > item.account_size * item.risk_percent / Decimal("100"):
        # Should not happen with planner math; still guard.
        reasons.append("max_loss_above_risk_budget")

    approved = len(reasons) == 0
    return VeskResult(
        symbol=item.symbol,
        approved=approved,
        shares=shares if approved else 0,
        max_loss=max_loss if approved else max_loss,
        reasons=reasons,
    )
