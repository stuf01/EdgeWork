"""Pure trade-journal statistics helpers (no I/O)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional, Sequence


ZERO = Decimal("0")


@dataclass(frozen=True)
class ClosedTrade:
    """Minimal closed-trade inputs for journal math."""

    actual_entry: Decimal
    actual_exit: Decimal
    shares_traded: int
    actual_risk: Optional[Decimal]
    setup_tag: Optional[str]
    closed_at: datetime
    checklist_score: Optional[int] = None


@dataclass(frozen=True)
class JournalStats:
    """Aggregate stats for a set of closed trades."""

    total_trades: int
    wins: int
    losses: int
    win_rate: Decimal
    avg_win: Decimal
    avg_loss: Decimal
    avg_r: Optional[Decimal]
    expectancy_r: Optional[Decimal]
    total_pnl: Decimal
    best_trade: Optional[Decimal]
    worst_trade: Optional[Decimal]
    max_drawdown: Decimal


def realized_pnl(
    actual_entry: Decimal,
    actual_exit: Decimal,
    shares_traded: int,
) -> Decimal:
    """Dollar P&L for a closed long: (exit - entry) * shares."""
    return (actual_exit - actual_entry) * Decimal(shares_traded)


def r_multiple(
    pnl: Decimal,
    actual_risk: Optional[Decimal],
) -> Optional[Decimal]:
    """R multiple = realized_pnl / planned actual_risk dollars."""
    if actual_risk is None or actual_risk == ZERO:
        return None
    return pnl / actual_risk


def compute_stats(closed_trades: Sequence[ClosedTrade]) -> JournalStats:
    """Compute overall journal stats for closed trades."""
    if not closed_trades:
        return JournalStats(
            total_trades=0,
            wins=0,
            losses=0,
            win_rate=ZERO,
            avg_win=ZERO,
            avg_loss=ZERO,
            avg_r=None,
            expectancy_r=None,
            total_pnl=ZERO,
            best_trade=None,
            worst_trade=None,
            max_drawdown=ZERO,
        )

    pnls: list[Decimal] = []
    rs: list[Decimal] = []
    for trade in closed_trades:
        pnl = realized_pnl(
            trade.actual_entry,
            trade.actual_exit,
            trade.shares_traded,
        )
        pnls.append(pnl)
        r_val = r_multiple(pnl, trade.actual_risk)
        if r_val is not None:
            rs.append(r_val)

    wins_list = [p for p in pnls if p > ZERO]
    losses_list = [p for p in pnls if p < ZERO]
    wins = len(wins_list)
    losses = len(losses_list)
    total = len(pnls)
    win_rate = (Decimal(wins) / Decimal(total)) if total else ZERO

    avg_win = (
        sum(wins_list, ZERO) / Decimal(len(wins_list)) if wins_list else ZERO
    )
    avg_loss = (
        sum(losses_list, ZERO) / Decimal(len(losses_list))
        if losses_list
        else ZERO
    )

    avg_r: Optional[Decimal] = None
    expectancy_r: Optional[Decimal] = None
    if rs:
        avg_r = sum(rs, ZERO) / Decimal(len(rs))
        r_values = _r_for_each(closed_trades, pnls)
        win_rs = [
            r
            for r, p in zip(r_values, pnls)
            if p > ZERO and r is not None
        ]
        loss_rs = [
            r
            for r, p in zip(r_values, pnls)
            if p < ZERO and r is not None
        ]
        avg_win_r = (
            sum(win_rs, ZERO) / Decimal(len(win_rs)) if win_rs else ZERO
        )
        avg_loss_r = (
            sum(loss_rs, ZERO) / Decimal(len(loss_rs)) if loss_rs else ZERO
        )
        loss_rate = (Decimal(losses) / Decimal(total)) if total else ZERO
        expectancy_r = (win_rate * avg_win_r) + (loss_rate * avg_loss_r)

    total_pnl = sum(pnls, ZERO)
    best_trade = max(pnls)
    worst_trade = min(pnls)
    max_dd = _max_drawdown(closed_trades, pnls)

    return JournalStats(
        total_trades=total,
        wins=wins,
        losses=losses,
        win_rate=win_rate,
        avg_win=avg_win,
        avg_loss=avg_loss,
        avg_r=avg_r,
        expectancy_r=expectancy_r,
        total_pnl=total_pnl,
        best_trade=best_trade,
        worst_trade=worst_trade,
        max_drawdown=max_dd,
    )


def stats_by_tag(
    closed_trades: Sequence[ClosedTrade],
) -> dict[str, JournalStats]:
    """Group stats by setup_tag; null tags become 'untagged'."""
    groups: dict[str, list[ClosedTrade]] = {}
    for trade in closed_trades:
        tag = trade.setup_tag.strip() if trade.setup_tag else ""
        key = tag if tag else "untagged"
        groups.setdefault(key, []).append(trade)
    return {tag: compute_stats(rows) for tag, rows in sorted(groups.items())}


@dataclass(frozen=True)
class ChecklistScoreGroupStats:
    """Lightweight stats for met vs below checklist score."""

    count: int
    win_rate: Decimal
    expectancy_r: Optional[Decimal]


def stats_by_checklist_score(
    closed_trades: Sequence[ClosedTrade],
    *,
    threshold: int = 70,
) -> dict[str, ChecklistScoreGroupStats]:
    """Compare closed trades with score >= threshold vs below (scored only)."""
    met = [t for t in closed_trades if t.checklist_score is not None and t.checklist_score >= threshold]
    below = [t for t in closed_trades if t.checklist_score is not None and t.checklist_score < threshold]
    return {
        "met": _score_group_stats(met),
        "below": _score_group_stats(below),
    }


def _score_group_stats(trades: Sequence[ClosedTrade]) -> ChecklistScoreGroupStats:
    stats = compute_stats(trades)
    return ChecklistScoreGroupStats(
        count=stats.total_trades,
        win_rate=stats.win_rate,
        expectancy_r=stats.expectancy_r,
    )


def cumulative_pnl_series(
    closed_trades: Sequence[ClosedTrade],
) -> list[tuple[datetime, Decimal]]:
    """Cumulative P&L points ordered by closed_at (then insertion order)."""
    ordered = sorted(
        enumerate(closed_trades),
        key=lambda item: (item[1].closed_at, item[0]),
    )
    points: list[tuple[datetime, Decimal]] = []
    running = ZERO
    for _, trade in ordered:
        running += realized_pnl(
            trade.actual_entry,
            trade.actual_exit,
            trade.shares_traded,
        )
        points.append((trade.closed_at, running))
    return points


def _r_for_each(
    closed_trades: Sequence[ClosedTrade],
    pnls: Sequence[Decimal],
) -> list[Optional[Decimal]]:
    return [
        r_multiple(pnl, trade.actual_risk)
        for trade, pnl in zip(closed_trades, pnls)
    ]


def _max_drawdown(
    closed_trades: Sequence[ClosedTrade],
    pnls: Sequence[Decimal],
) -> Decimal:
    """Largest peak-to-trough drop in cumulative P&L by close time."""
    if not closed_trades:
        return ZERO
    ordered = sorted(
        zip(closed_trades, pnls),
        key=lambda item: (item[0].closed_at, id(item[0])),
    )
    running = ZERO
    peak = ZERO
    max_dd = ZERO
    for _, pnl in ordered:
        running += pnl
        if running > peak:
            peak = running
        drop = peak - running
        if drop > max_dd:
            max_dd = drop
    return max_dd
