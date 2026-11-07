"""Unit tests for the pure daily gap-breakout backtester."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from app.backtest import (
    BacktestParams,
    compute_entry,
    prior_rel_volume,
    run_backtest,
    simulate_intraday_exit,
    try_trade_for_day,
)
from app.providers.base import Bar


def _bar(
    day: date,
    o: str,
    h: str,
    low: str,
    c: str,
    volume: int = 1_000_000,
) -> Bar:
    return Bar(
        date=day,
        open=Decimal(o),
        high=Decimal(h),
        low=Decimal(low),
        close=Decimal(c),
        volume=volume,
    )


def _history(
    end: date,
    n: int = 25,
    close: str = "10",
    volume: int = 1_000_000,
) -> list[Bar]:
    """Build ``n`` flat prior bars ending the day before ``end``."""
    bars: list[Bar] = []
    price = Decimal(close)
    for i in range(n, 0, -1):
        day = end - timedelta(days=i)
        bars.append(
            Bar(
                date=day,
                open=price,
                high=price + Decimal("0.20"),
                low=price - Decimal("0.20"),
                close=price,
                volume=volume,
            )
        )
    return bars


def test_winning_trade_target_hit() -> None:
    """Gap + breakout, high reaches target, low stays above stop."""
    day = date(2026, 3, 10)
    # Prior close 10; open gaps to 10.30 (+3%); prev high 10.20
    hist = _history(day, close="10.00")
    prev = hist[-1]
    # Ensure prev high is known
    hist[-1] = Bar(
        date=prev.date,
        open=Decimal("10"),
        high=Decimal("10.20"),
        low=Decimal("9.90"),
        close=Decimal("10.00"),
        volume=2_000_000,
    )
    # Gap open below trigger; high breaks prev high so entry fills at trigger.
    today = _bar(day, "10.20", "10.80", "10.18", "10.70")
    bars = hist + [today]
    params = BacktestParams(
        min_gap_percent=Decimal("2"),
        min_relative_volume=Decimal("1"),
        min_avg_volume=Decimal("100"),
        stop_percent=Decimal("2"),
        target_r=Decimal("2"),
        cost_per_share=Decimal("0"),
        starting_account=Decimal("10000"),
    )
    trade, skipped = try_trade_for_day("AAA", bars, len(bars) - 1, params, Decimal("10000"))
    assert skipped is False
    assert trade is not None
    # entry = prev.high + 0.01 = 10.21
    assert trade.entry == Decimal("10.21")
    # stop = 10.21 * 0.98
    assert trade.stop == Decimal("10.21") * Decimal("0.98")
    risk = trade.entry - trade.stop
    assert trade.target == trade.entry + Decimal("2") * risk
    assert trade.exit_reason == "target_hit"
    assert trade.exit == trade.target
    assert trade.pnl > 0


def test_losing_trade_stop_hit() -> None:
    day = date(2026, 3, 11)
    hist = _history(day, close="20.00")
    hist[-1] = Bar(
        date=hist[-1].date,
        open=Decimal("20"),
        high=Decimal("20.50"),
        low=Decimal("19.80"),
        close=Decimal("20.00"),
        volume=2_000_000,
    )
    # Gap open 20.60; breakout then sells off through stop
    today = _bar(day, "20.60", "20.70", "19.50", "19.80")
    bars = hist + [today]
    params = BacktestParams(
        min_relative_volume=Decimal("1"),
        min_avg_volume=Decimal("100"),
        cost_per_share=Decimal("0"),
    )
    trade, _ = try_trade_for_day("BBB", bars, len(bars) - 1, params, Decimal("10000"))
    assert trade is not None
    assert trade.exit_reason == "stop_hit"
    assert trade.exit == trade.stop
    assert trade.pnl < 0


def test_exit_at_close() -> None:
    day = date(2026, 3, 12)
    hist = _history(day, close="15.00")
    hist[-1] = Bar(
        date=hist[-1].date,
        open=Decimal("15"),
        high=Decimal("15.40"),
        low=Decimal("14.90"),
        close=Decimal("15.00"),
        volume=2_000_000,
    )
    # Breaks high but neither stop nor target
    today = _bar(day, "15.40", "15.55", "15.35", "15.50")
    bars = hist + [today]
    params = BacktestParams(
        min_relative_volume=Decimal("1"),
        min_avg_volume=Decimal("100"),
        stop_percent=Decimal("5"),
        target_r=Decimal("5"),
        cost_per_share=Decimal("0"),
    )
    trade, _ = try_trade_for_day("CCC", bars, len(bars) - 1, params, Decimal("10000"))
    assert trade is not None
    assert trade.exit_reason == "close"
    assert trade.exit == Decimal("15.50")


def test_same_bar_stop_and_target_assumes_stop_first() -> None:
    day = date(2026, 3, 13)
    hist = _history(day, close="30.00")
    hist[-1] = Bar(
        date=hist[-1].date,
        open=Decimal("30"),
        high=Decimal("30.50"),
        low=Decimal("29.80"),
        close=Decimal("30.00"),
        volume=2_000_000,
    )
    today = _bar(day, "30.80", "40.00", "10.00", "35.00")
    bars = hist + [today]
    params = BacktestParams(
        min_relative_volume=Decimal("1"),
        min_avg_volume=Decimal("100"),
        cost_per_share=Decimal("0"),
    )
    trade, _ = try_trade_for_day("DDD", bars, len(bars) - 1, params, Decimal("10000"))
    assert trade is not None
    assert trade.exit_reason == "stop_hit"
    assert trade.pnl < 0


def test_gap_open_above_entry_fills_at_open() -> None:
    day = date(2026, 3, 14)
    hist = _history(day, close="25.00")
    hist[-1] = Bar(
        date=hist[-1].date,
        open=Decimal("25"),
        high=Decimal("25.20"),
        low=Decimal("24.90"),
        close=Decimal("25.00"),
        volume=2_000_000,
    )
    # Open already above prev.high + 0.01
    today = _bar(day, "25.50", "26.00", "25.40", "25.80")
    bars = hist + [today]
    params = BacktestParams(
        min_relative_volume=Decimal("1"),
        min_avg_volume=Decimal("100"),
        cost_per_share=Decimal("0"),
    )
    entry = compute_entry(today, hist[-1], "break_prev_high")
    assert entry == Decimal("25.50")
    trade, _ = try_trade_for_day("EEE", bars, len(bars) - 1, params, Decimal("10000"))
    assert trade is not None
    assert trade.entry == Decimal("25.50")


def test_skip_day_for_too_little_history() -> None:
    day = date(2026, 3, 15)
    bars = [_bar(day - timedelta(days=1), "10", "10.2", "9.9", "10")] + [
        _bar(day, "10.3", "10.5", "10.2", "10.4")
    ]
    params = BacktestParams(min_avg_volume=Decimal("1"), min_relative_volume=Decimal("0.1"))
    trade, skipped = try_trade_for_day("FFF", bars, 1, params, Decimal("10000"))
    assert skipped is True
    assert trade is None


def test_costs_are_subtracted() -> None:
    day = date(2026, 3, 16)
    hist = _history(day, close="10.00")
    hist[-1] = Bar(
        date=hist[-1].date,
        open=Decimal("10"),
        high=Decimal("10.20"),
        low=Decimal("9.90"),
        close=Decimal("10.00"),
        volume=2_000_000,
    )
    today = _bar(day, "10.30", "10.80", "10.25", "10.70")
    bars = hist + [today]
    params_free = BacktestParams(
        min_relative_volume=Decimal("1"),
        min_avg_volume=Decimal("100"),
        cost_per_share=Decimal("0"),
    )
    params_cost = BacktestParams(
        min_relative_volume=Decimal("1"),
        min_avg_volume=Decimal("100"),
        cost_per_share=Decimal("0.02"),
    )
    free, _ = try_trade_for_day("GGG", bars, len(bars) - 1, params_free, Decimal("10000"))
    costly, _ = try_trade_for_day("GGG", bars, len(bars) - 1, params_cost, Decimal("10000"))
    assert free is not None and costly is not None
    assert free.shares == costly.shares
    assert costly.pnl == free.pnl - (Decimal("0.02") * Decimal(costly.shares))


def test_no_lookahead_on_today_volume() -> None:
    """Changing today's volume must not change qualification / entry decision."""
    day = date(2026, 3, 17)
    hist = _history(day, close="12.00")
    hist[-1] = Bar(
        date=hist[-1].date,
        open=Decimal("12"),
        high=Decimal("12.30"),
        low=Decimal("11.90"),
        close=Decimal("12.00"),
        volume=2_000_000,
    )
    today_a = _bar(day, "12.40", "12.80", "12.35", "12.70", volume=100)
    today_b = _bar(day, "12.40", "12.80", "12.35", "12.70", volume=50_000_000)
    params = BacktestParams(
        min_relative_volume=Decimal("1"),
        min_avg_volume=Decimal("100"),
        cost_per_share=Decimal("0"),
    )
    trade_a, _ = try_trade_for_day(
        "HHH",
        hist + [today_a],
        len(hist),
        params,
        Decimal("10000"),
    )
    trade_b, _ = try_trade_for_day(
        "HHH",
        hist + [today_b],
        len(hist),
        params,
        Decimal("10000"),
    )
    assert trade_a is not None and trade_b is not None
    assert trade_a.entry == trade_b.entry
    assert trade_a.stop == trade_b.stop
    assert trade_a.target == trade_b.target
    assert trade_a.exit == trade_b.exit
    # Rel volume uses prior day — identical regardless of today's volume
    assert prior_rel_volume(hist + [today_a], len(hist)) == prior_rel_volume(
        hist + [today_b],
        len(hist),
    )


def test_simulate_conflict_helper() -> None:
    today = _bar(date(2026, 1, 1), "10", "12", "8", "11")
    exit_px, reason = simulate_intraday_exit(
        today,
        Decimal("10"),
        Decimal("9"),
        Decimal("11"),
    )
    assert reason == "stop_hit"
    assert exit_px == Decimal("9")


def test_run_backtest_produces_equity_curve() -> None:
    day = date(2026, 4, 1)
    hist = _history(day, close="10.00")
    hist[-1] = Bar(
        date=hist[-1].date,
        open=Decimal("10"),
        high=Decimal("10.20"),
        low=Decimal("9.90"),
        close=Decimal("10.00"),
        volume=2_000_000,
    )
    today = _bar(day, "10.30", "10.80", "10.25", "10.70")
    bars = hist + [today]
    result = run_backtest(
        {"ZZZ": bars},
        start_date=day,
        end_date=day,
        params=BacktestParams(
            min_relative_volume=Decimal("1"),
            min_avg_volume=Decimal("100"),
            cost_per_share=Decimal("0"),
        ),
    )
    assert len(result.trades) == 1
    assert result.summary is not None
    assert result.summary.total_trades == 1
    assert len(result.equity_curve) == 1
    assert result.equity_curve[0].equity > Decimal("10000")


def test_skip_earnings_days_filters_trades() -> None:
    day = date(2026, 4, 1)
    hist = _history(day, close="10.00")
    hist[-1] = Bar(
        date=hist[-1].date,
        open=Decimal("10"),
        high=Decimal("10.20"),
        low=Decimal("9.90"),
        close=Decimal("10.00"),
        volume=2_000_000,
    )
    today = _bar(day, "10.30", "10.80", "10.25", "10.70")
    bars = hist + [today]
    params = BacktestParams(
        min_relative_volume=Decimal("1"),
        min_avg_volume=Decimal("100"),
        cost_per_share=Decimal("0"),
        skip_earnings_days=2,
    )
    skipped = run_backtest(
        {"ZZZ": bars},
        start_date=day,
        end_date=day,
        params=params,
        earnings_dates_by_symbol={"ZZZ": [day + timedelta(days=1)]},
    )
    assert skipped.trades == []
    assert skipped.earnings_trades_skipped == 1

    allowed = run_backtest(
        {"ZZZ": bars},
        start_date=day,
        end_date=day,
        params=params,
        earnings_dates_by_symbol={"ZZZ": [day + timedelta(days=10)]},
    )
    assert len(allowed.trades) == 1
    assert allowed.earnings_trades_skipped == 0
