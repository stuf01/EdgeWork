"""Pure daily gap-and-breakout backtester (no I/O).

Lookahead rule
--------------
Qualification (gap %, relative volume, min price, avg volume) uses ONLY
information known at or before the day's open. Relative volume is computed
from the PREVIOUS day's volume vs that day's prior 20-day average — never
from today's volume. Today's high/low/close/volume are used only after
qualification, to evaluate the breakout trigger and simulate the trade.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from math import floor
from typing import Optional, Sequence

from app.earnings import is_within_earnings_window
from app.journal import ClosedTrade, JournalStats, compute_stats
from app.providers.base import Bar
from app.scanner import avg_daily_volume, gap_percent, relative_volume

ZERO = Decimal("0")
CENT = Decimal("0.01")
MAX_SYMBOLS = 50
MAX_HISTORY_YEARS = 3
HISTORY_BARS_REQUIRED = 20
MAX_TRADES_PER_DAY = 5

STOP_RULES = ("fixed_percent", "prev_day_low", "today_open")
ENTRY_RULES = ("break_prev_high",)


@dataclass(frozen=True)
class BacktestParams:
    """Tunable backtest parameters."""

    min_gap_percent: Decimal = Decimal("2")
    min_relative_volume: Decimal = Decimal("2")
    min_price: Decimal = Decimal("5")
    min_avg_volume: Decimal = Decimal("500000")
    entry_rule: str = "break_prev_high"
    stop_rule: str = "fixed_percent"
    stop_percent: Decimal = Decimal("2")
    target_r: Decimal = Decimal("2")
    cost_per_share: Decimal = Decimal("0.02")
    risk_per_trade_percent: Decimal = Decimal("1")
    starting_account: Decimal = Decimal("10000")
    skip_earnings_days: int = 0


@dataclass(frozen=True)
class BacktestTrade:
    """One simulated trade."""

    symbol: str
    date: date
    entry: Decimal
    stop: Decimal
    target: Decimal
    exit: Decimal
    exit_reason: str
    shares: int
    pnl: Decimal
    r_multiple: Decimal
    gap_percent: Decimal


@dataclass(frozen=True)
class EquityPoint:
    """Account equity after a trade."""

    date: date
    equity: Decimal


@dataclass
class BacktestResult:
    """Full backtest output."""

    trades: list[BacktestTrade] = field(default_factory=list)
    summary: Optional[JournalStats] = None
    equity_curve: list[EquityPoint] = field(default_factory=list)
    by_year: dict[int, JournalStats] = field(default_factory=dict)
    errors: list[dict[str, str]] = field(default_factory=list)
    skipped_days: int = 0
    earnings_trades_skipped: int = 0
    earnings_data_unavailable: bool = False


def validate_params(params: BacktestParams) -> None:
    """Raise ValueError if parameters are invalid."""
    if params.min_gap_percent < 0:
        raise ValueError("min_gap_percent must be >= 0")
    if params.min_relative_volume <= 0:
        raise ValueError("min_relative_volume must be > 0")
    if params.min_price <= 0:
        raise ValueError("min_price must be > 0")
    if params.min_avg_volume < 0:
        raise ValueError("min_avg_volume must be >= 0")
    if params.entry_rule not in ENTRY_RULES:
        raise ValueError(f"entry_rule must be one of {ENTRY_RULES}")
    if params.stop_rule not in STOP_RULES:
        raise ValueError(f"stop_rule must be one of {STOP_RULES}")
    if params.stop_percent <= 0 or params.stop_percent >= 100:
        raise ValueError("stop_percent must be between 0 and 100 exclusive")
    if params.target_r <= 0:
        raise ValueError("target_r must be > 0")
    if params.cost_per_share < 0:
        raise ValueError("cost_per_share must be >= 0")
    if params.risk_per_trade_percent <= 0 or params.risk_per_trade_percent > 100:
        raise ValueError("risk_per_trade_percent must be > 0 and <= 100")
    if params.starting_account <= 0:
        raise ValueError("starting_account must be > 0")
    if params.skip_earnings_days < 0:
        raise ValueError("skip_earnings_days must be >= 0")


def validate_run_limits(
    symbols: Sequence[str],
    start_date: date,
    end_date: date,
) -> None:
    """Enforce symbol count and history window limits."""
    if start_date > end_date:
        raise ValueError("start_date must be on or before end_date")
    if len(symbols) > MAX_SYMBOLS:
        raise ValueError(f"At most {MAX_SYMBOLS} symbols are allowed per run")
    span_days = (end_date - start_date).days
    if span_days > MAX_HISTORY_YEARS * 366:
        raise ValueError(
            f"Date range cannot exceed {MAX_HISTORY_YEARS} years"
        )


def prior_rel_volume(bars: Sequence[Bar], day_index: int) -> Optional[Decimal]:
    """Previous day's volume / average of the 20 days before that day."""
    if day_index < HISTORY_BARS_REQUIRED + 1:
        return None
    prev = bars[day_index - 1]
    # 20 bars ending the day before ``prev``: [day_index-21, day_index-1)
    window = bars[day_index - 21 : day_index - 1]
    if len(window) < HISTORY_BARS_REQUIRED:
        return None
    avg = avg_daily_volume(window, lookback=HISTORY_BARS_REQUIRED)
    return relative_volume(prev.volume, avg)


def prior_avg_volume(bars: Sequence[Bar], day_index: int) -> Optional[Decimal]:
    """Average volume of the 20 completed days before today."""
    if day_index < HISTORY_BARS_REQUIRED:
        return None
    window = bars[day_index - HISTORY_BARS_REQUIRED : day_index]
    return avg_daily_volume(window, lookback=HISTORY_BARS_REQUIRED)


def compute_entry(
    today: Bar,
    prev: Bar,
    entry_rule: str,
) -> Optional[Decimal]:
    """Return entry price if breakout triggers, else None."""
    if entry_rule != "break_prev_high":
        return None
    trigger = prev.high + CENT
    # Breakout trigger may use today's high; open decides fill if already above.
    if today.high <= prev.high:
        return None
    if today.open >= trigger:
        return today.open
    return trigger


def compute_stop(
    entry: Decimal,
    today: Bar,
    prev: Bar,
    params: BacktestParams,
) -> Optional[Decimal]:
    """Return stop below entry, or None if invalid."""
    if params.stop_rule == "fixed_percent":
        stop = entry * (Decimal("1") - params.stop_percent / Decimal("100"))
    elif params.stop_rule == "prev_day_low":
        stop = prev.low
    elif params.stop_rule == "today_open":
        stop = today.open
    else:
        return None
    if stop >= entry:
        return None
    return stop


def simulate_intraday_exit(
    today: Bar,
    entry: Decimal,
    stop: Decimal,
    target: Decimal,
) -> tuple[Decimal, str]:
    """Simulate exit within today's OHLC bar.

    If both stop and target are reachable in the same bar, assume STOP first.
    """
    stop_hit = today.low <= stop
    target_hit = today.high >= target
    if stop_hit and target_hit:
        return stop, "stop_hit"
    if stop_hit:
        return stop, "stop_hit"
    if target_hit:
        return target, "target_hit"
    return today.close, "close"


def size_shares(
    account: Decimal,
    risk_percent: Decimal,
    entry: Decimal,
    stop: Decimal,
) -> int:
    """Planner-style whole-share sizing from account risk."""
    if account <= 0 or entry <= stop:
        return 0
    max_risk = account * risk_percent / Decimal("100")
    risk_per_share = entry - stop
    if risk_per_share <= 0:
        return 0
    return floor(max_risk / risk_per_share)


def try_trade_for_day(
    symbol: str,
    bars: Sequence[Bar],
    day_index: int,
    params: BacktestParams,
    account: Decimal,
) -> tuple[Optional[BacktestTrade], bool]:
    """Evaluate one symbol-day. Returns (trade_or_None, skipped_for_history)."""
    if day_index < HISTORY_BARS_REQUIRED + 1:
        return None, True

    today = bars[day_index]
    prev = bars[day_index - 1]

    # --- Qualification (open / prior data only; see module lookahead rule) ---
    gap = gap_percent(today.open, prev.close)
    if gap is None or gap < params.min_gap_percent:
        return None, False

    rel = prior_rel_volume(bars, day_index)
    if rel is None or rel < params.min_relative_volume:
        return None, False

    if today.open < params.min_price:
        return None, False

    avg_vol = prior_avg_volume(bars, day_index)
    if avg_vol is None or avg_vol < params.min_avg_volume:
        return None, False

    entry = compute_entry(today, prev, params.entry_rule)
    if entry is None:
        return None, False

    stop = compute_stop(entry, today, prev, params)
    if stop is None:
        return None, False

    risk_per_share = entry - stop
    target = entry + params.target_r * risk_per_share
    shares = size_shares(
        account,
        params.risk_per_trade_percent,
        entry,
        stop,
    )
    if shares <= 0:
        return None, False

    exit_price, reason = simulate_intraday_exit(today, entry, stop, target)
    gross = (exit_price - entry) * Decimal(shares)
    costs = params.cost_per_share * Decimal(shares)
    pnl = gross - costs
    planned_risk = risk_per_share * Decimal(shares)
    r_mult = (pnl / planned_risk) if planned_risk != ZERO else ZERO

    trade = BacktestTrade(
        symbol=symbol,
        date=today.date,
        entry=entry,
        stop=stop,
        target=target,
        exit=exit_price,
        exit_reason=reason,
        shares=shares,
        pnl=pnl,
        r_multiple=r_mult,
        gap_percent=gap,
    )
    return trade, False


def run_backtest(
    symbol_bars: dict[str, Sequence[Bar]],
    start_date: date,
    end_date: date,
    params: BacktestParams,
    errors: Optional[list[dict[str, str]]] = None,
    earnings_dates_by_symbol: Optional[dict[str, Sequence[date]]] = None,
    earnings_data_unavailable: bool = False,
) -> BacktestResult:
    """Run the gap-breakout backtest across symbols and date range."""
    validate_params(params)
    validate_run_limits(list(symbol_bars.keys()), start_date, end_date)

    # Collect trading days in range that appear in any series.
    all_dates: set[date] = set()
    indexed: dict[str, list[Bar]] = {}
    for symbol, bars in symbol_bars.items():
        ordered = sorted(bars, key=lambda b: b.date)
        indexed[symbol] = ordered
        for bar in ordered:
            if start_date <= bar.date <= end_date:
                all_dates.add(bar.date)

    equity = params.starting_account
    trades: list[BacktestTrade] = []
    equity_curve: list[EquityPoint] = []
    skipped = 0
    earnings_skipped = 0
    earnings_map = earnings_dates_by_symbol or {}

    for day in sorted(all_dates):
        candidates: list[BacktestTrade] = []
        for symbol, bars in indexed.items():
            # Find index of this date
            idx = _index_on_date(bars, day)
            if idx is None:
                continue
            trade, was_skipped = try_trade_for_day(
                symbol,
                bars,
                idx,
                params,
                equity,
            )
            if was_skipped:
                skipped += 1
            if trade is None:
                continue
            if params.skip_earnings_days > 0 and is_within_earnings_window(
                trade.date,
                earnings_map.get(symbol, ()),
                params.skip_earnings_days,
            ):
                earnings_skipped += 1
                continue
            candidates.append(trade)

        # Largest gaps first; at most one per symbol already; max 5/day.
        candidates.sort(key=lambda t: t.gap_percent, reverse=True)
        taken = 0
        for trade in candidates:
            if taken >= MAX_TRADES_PER_DAY:
                break
            # Re-size against current equity (gap ranking used prior equity;
            # recompute shares with latest equity for consistency).
            sized = _resize_trade(trade, equity, params)
            if sized is None:
                continue
            trades.append(sized)
            equity = equity + sized.pnl
            equity_curve.append(EquityPoint(date=sized.date, equity=equity))
            taken += 1

    closed = [
        ClosedTrade(
            actual_entry=t.entry,
            actual_exit=t.exit,
            shares_traded=t.shares,
            actual_risk=(t.entry - t.stop) * Decimal(t.shares),
            setup_tag=None,
            closed_at=datetime(
                t.date.year,
                t.date.month,
                t.date.day,
                20,
                0,
                tzinfo=timezone.utc,
            ),
        )
        for t in trades
    ]
    # Use trade pnl (already includes costs) via a thin adapter for stats:
    # compute_stats recalculates pnl from entry/exit without costs, so build
    # summary from trade.pnl directly for total_pnl while reusing win/loss math.
    summary = _summary_from_backtest_trades(trades)
    by_year: dict[int, JournalStats] = {}
    years = sorted({t.date.year for t in trades})
    for year in years:
        year_trades = [t for t in trades if t.date.year == year]
        by_year[year] = _summary_from_backtest_trades(year_trades)

    return BacktestResult(
        trades=trades,
        summary=summary,
        equity_curve=equity_curve,
        by_year=by_year,
        errors=list(errors or []),
        skipped_days=skipped,
        earnings_trades_skipped=earnings_skipped,
        earnings_data_unavailable=bool(earnings_data_unavailable),
    )


def _summary_from_backtest_trades(trades: Sequence[BacktestTrade]) -> JournalStats:
    """Stats using each trade's after-cost pnl and r_multiple."""
    if not trades:
        return compute_stats([])

    # Map into ClosedTrade for drawdown ordering, but override totals below.
    closed = [
        ClosedTrade(
            actual_entry=t.entry,
            actual_exit=t.exit,
            shares_traded=t.shares,
            actual_risk=(t.entry - t.stop) * Decimal(t.shares),
            setup_tag=None,
            closed_at=datetime(
                t.date.year,
                t.date.month,
                t.date.day,
                20,
                0,
                tzinfo=timezone.utc,
            ),
        )
        for t in trades
    ]
    base = compute_stats(closed)

    pnls = [t.pnl for t in trades]
    wins_list = [p for p in pnls if p > ZERO]
    losses_list = [p for p in pnls if p < ZERO]
    wins = len(wins_list)
    losses = len(losses_list)
    total = len(pnls)
    win_rate = (Decimal(wins) / Decimal(total)) if total else ZERO
    avg_win = sum(wins_list, ZERO) / Decimal(wins) if wins else ZERO
    avg_loss = sum(losses_list, ZERO) / Decimal(losses) if losses else ZERO
    rs = [t.r_multiple for t in trades]
    avg_r = sum(rs, ZERO) / Decimal(len(rs)) if rs else None
    win_rs = [t.r_multiple for t in trades if t.pnl > ZERO]
    loss_rs = [t.r_multiple for t in trades if t.pnl < ZERO]
    avg_win_r = sum(win_rs, ZERO) / Decimal(len(win_rs)) if win_rs else ZERO
    avg_loss_r = sum(loss_rs, ZERO) / Decimal(len(loss_rs)) if loss_rs else ZERO
    loss_rate = (Decimal(losses) / Decimal(total)) if total else ZERO
    expectancy_r = (win_rate * avg_win_r) + (loss_rate * avg_loss_r) if rs else None

    # Drawdown from after-cost equity path
    max_dd = _max_drawdown_from_pnls(pnls)

    return JournalStats(
        total_trades=total,
        wins=wins,
        losses=losses,
        win_rate=win_rate,
        avg_win=avg_win,
        avg_loss=avg_loss,
        avg_r=avg_r,
        expectancy_r=expectancy_r,
        total_pnl=sum(pnls, ZERO),
        best_trade=max(pnls) if pnls else None,
        worst_trade=min(pnls) if pnls else None,
        max_drawdown=max_dd,
    )


def _max_drawdown_from_pnls(pnls: Sequence[Decimal]) -> Decimal:
    running = ZERO
    peak = ZERO
    max_dd = ZERO
    for pnl in pnls:
        running += pnl
        if running > peak:
            peak = running
        drop = peak - running
        if drop > max_dd:
            max_dd = drop
    return max_dd


def _index_on_date(bars: Sequence[Bar], day: date) -> Optional[int]:
    for i, bar in enumerate(bars):
        if bar.date == day:
            return i
    return None


def _resize_trade(
    trade: BacktestTrade,
    account: Decimal,
    params: BacktestParams,
) -> Optional[BacktestTrade]:
    shares = size_shares(
        account,
        params.risk_per_trade_percent,
        trade.entry,
        trade.stop,
    )
    if shares <= 0:
        return None
    risk_per_share = trade.entry - trade.stop
    gross = (trade.exit - trade.entry) * Decimal(shares)
    costs = params.cost_per_share * Decimal(shares)
    pnl = gross - costs
    planned_risk = risk_per_share * Decimal(shares)
    r_mult = (pnl / planned_risk) if planned_risk != ZERO else ZERO
    return BacktestTrade(
        symbol=trade.symbol,
        date=trade.date,
        entry=trade.entry,
        stop=trade.stop,
        target=trade.target,
        exit=trade.exit,
        exit_reason=trade.exit_reason,
        shares=shares,
        pnl=pnl,
        r_multiple=r_mult,
        gap_percent=trade.gap_percent,
    )
