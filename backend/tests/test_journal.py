"""Unit tests for journal P&L and stats helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from app.journal import (
    ClosedTrade,
    compute_stats,
    realized_pnl,
    r_multiple,
    stats_by_tag,
)


def _trade(
    entry: str,
    exit_: str,
    shares: int,
    risk: str | None,
    closed_at: datetime,
    tag: str | None = None,
) -> ClosedTrade:
    return ClosedTrade(
        actual_entry=Decimal(entry),
        actual_exit=Decimal(exit_),
        shares_traded=shares,
        actual_risk=Decimal(risk) if risk is not None else None,
        setup_tag=tag,
        closed_at=closed_at,
    )


def test_realized_pnl() -> None:
    assert realized_pnl(Decimal("10"), Decimal("12"), 100) == Decimal("200")
    assert realized_pnl(Decimal("10"), Decimal("9"), 50) == Decimal("-50")


def test_r_multiple() -> None:
    assert r_multiple(Decimal("150"), Decimal("100")) == Decimal("1.5")
    assert r_multiple(Decimal("50"), Decimal("0")) is None
    assert r_multiple(Decimal("50"), None) is None


def test_compute_stats_empty() -> None:
    stats = compute_stats([])
    assert stats.total_trades == 0
    assert stats.wins == 0
    assert stats.losses == 0
    assert stats.win_rate == Decimal("0")
    assert stats.avg_win == Decimal("0")
    assert stats.avg_loss == Decimal("0")
    assert stats.avg_r is None
    assert stats.expectancy_r is None
    assert stats.total_pnl == Decimal("0")
    assert stats.best_trade is None
    assert stats.worst_trade is None
    assert stats.max_drawdown == Decimal("0")


def test_compute_stats_all_wins() -> None:
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    trades = [
        _trade("10", "11", 10, "10", t0, "breakout"),
        _trade("20", "22", 5, "10", t0, "breakout"),
    ]
    # pnl: 10, 10
    stats = compute_stats(trades)
    assert stats.total_trades == 2
    assert stats.wins == 2
    assert stats.losses == 0
    assert stats.win_rate == Decimal("1")
    assert stats.avg_win == Decimal("10")
    assert stats.avg_loss == Decimal("0")
    assert stats.total_pnl == Decimal("20")
    assert stats.best_trade == Decimal("10")
    assert stats.worst_trade == Decimal("10")
    assert stats.max_drawdown == Decimal("0")
    assert stats.avg_r == Decimal("1")
    assert stats.expectancy_r == Decimal("1")


def test_compute_stats_all_losses() -> None:
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    trades = [
        _trade("10", "9", 10, "10", t0),
        _trade("20", "18", 5, "10", t0),
    ]
    # pnl: -10, -10
    stats = compute_stats(trades)
    assert stats.wins == 0
    assert stats.losses == 2
    assert stats.win_rate == Decimal("0")
    assert stats.avg_win == Decimal("0")
    assert stats.avg_loss == Decimal("-10")
    assert stats.total_pnl == Decimal("-20")
    assert stats.expectancy_r == Decimal("-1")


def test_max_drawdown_hand_calculated() -> None:
    """Cumulative: +100, +150, +70, +30, +60 -> peak 150 to trough 30 = 120."""
    base = datetime(2026, 2, 1, tzinfo=timezone.utc)
    trades = [
        _trade("10", "11", 100, "100", base.replace(day=1)),  # +100
        _trade("10", "10.5", 100, "100", base.replace(day=2)),  # +50
        _trade("10", "9.2", 100, "100", base.replace(day=3)),  # -80
        _trade("10", "9.6", 100, "100", base.replace(day=4)),  # -40
        _trade("10", "10.3", 100, "100", base.replace(day=5)),  # +30
    ]
    stats = compute_stats(trades)
    assert stats.total_pnl == Decimal("60")
    assert stats.max_drawdown == Decimal("120")
    assert stats.best_trade == Decimal("100")
    assert stats.worst_trade == Decimal("-80")


def test_stats_by_tag() -> None:
    t0 = datetime(2026, 3, 1, tzinfo=timezone.utc)
    trades = [
        _trade("10", "11", 10, "10", t0, "breakout"),
        _trade("10", "9", 10, "10", t0, None),
        _trade("10", "12", 10, "10", t0, "breakout"),
    ]
    by_tag = stats_by_tag(trades)
    assert set(by_tag.keys()) == {"breakout", "untagged"}
    assert by_tag["breakout"].total_trades == 2
    assert by_tag["breakout"].wins == 2
    assert by_tag["untagged"].total_trades == 1
    assert by_tag["untagged"].losses == 1
