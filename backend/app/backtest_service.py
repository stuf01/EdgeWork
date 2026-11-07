"""I/O helpers for running and persisting backtests."""

from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.backtest import (
    MAX_HISTORY_YEARS,
    MAX_SYMBOLS,
    BacktestParams,
    BacktestResult,
    BacktestTrade,
    EquityPoint,
    run_backtest,
    validate_params,
    validate_run_limits,
)
from app.journal import JournalStats
from app.models import BacktestRun, WatchlistItem
from app.providers.base import Bar, MarketDataError, MarketDataProvider


def _dec(value: Any) -> str:
    if value is None:
        return None  # type: ignore[return-value]
    if isinstance(value, Decimal):
        return format(value, "f")
    return str(value)


def params_to_dict(params: BacktestParams) -> dict[str, Any]:
    return {
        "min_gap_percent": _dec(params.min_gap_percent),
        "min_relative_volume": _dec(params.min_relative_volume),
        "min_price": _dec(params.min_price),
        "min_avg_volume": _dec(params.min_avg_volume),
        "entry_rule": params.entry_rule,
        "stop_rule": params.stop_rule,
        "stop_percent": _dec(params.stop_percent),
        "target_r": _dec(params.target_r),
        "cost_per_share": _dec(params.cost_per_share),
        "risk_per_trade_percent": _dec(params.risk_per_trade_percent),
        "starting_account": _dec(params.starting_account),
    }


def stats_to_dict(stats: Optional[JournalStats]) -> dict[str, Any]:
    if stats is None:
        return {
            "total_trades": 0,
            "wins": 0,
            "losses": 0,
            "win_rate": "0",
            "avg_win": "0",
            "avg_loss": "0",
            "avg_r": None,
            "expectancy_r": None,
            "total_pnl": "0",
            "best_trade": None,
            "worst_trade": None,
            "max_drawdown": "0",
        }
    return {
        "total_trades": stats.total_trades,
        "wins": stats.wins,
        "losses": stats.losses,
        "win_rate": _dec(stats.win_rate),
        "avg_win": _dec(stats.avg_win),
        "avg_loss": _dec(stats.avg_loss),
        "avg_r": _dec(stats.avg_r) if stats.avg_r is not None else None,
        "expectancy_r": (
            _dec(stats.expectancy_r) if stats.expectancy_r is not None else None
        ),
        "total_pnl": _dec(stats.total_pnl),
        "best_trade": _dec(stats.best_trade) if stats.best_trade is not None else None,
        "worst_trade": (
            _dec(stats.worst_trade) if stats.worst_trade is not None else None
        ),
        "max_drawdown": _dec(stats.max_drawdown),
    }


def trade_to_dict(trade: BacktestTrade) -> dict[str, Any]:
    return {
        "symbol": trade.symbol,
        "date": trade.date.isoformat(),
        "entry": _dec(trade.entry),
        "stop": _dec(trade.stop),
        "target": _dec(trade.target),
        "exit": _dec(trade.exit),
        "exit_reason": trade.exit_reason,
        "shares": trade.shares,
        "pnl": _dec(trade.pnl),
        "r_multiple": _dec(trade.r_multiple),
        "gap_percent": _dec(trade.gap_percent),
    }


def equity_to_dict(point: EquityPoint) -> dict[str, Any]:
    return {"date": point.date.isoformat(), "equity": _dec(point.equity)}


def result_payload(
    result: BacktestResult,
    *,
    params: BacktestParams,
    symbols: list[str],
    start_date: date,
    end_date: date,
    name: Optional[str] = None,
    run_id: Optional[int] = None,
    created_at: Optional[datetime] = None,
) -> dict[str, Any]:
    return {
        "id": run_id,
        "created_at": created_at.isoformat() if created_at else None,
        "name": name,
        "parameters": params_to_dict(params),
        "symbols": symbols,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "summary": stats_to_dict(result.summary),
        "by_year": {
            str(year): stats_to_dict(stats) for year, stats in result.by_year.items()
        },
        "equity_curve": [equity_to_dict(p) for p in result.equity_curve],
        "trades": [trade_to_dict(t) for t in result.trades],
        "errors": result.errors,
        "skipped_days": result.skipped_days,
    }


def _unwrap_saved_summary(blob: Any) -> dict[str, Any]:
    """Normalize the JSON stored in BacktestRun.summary.

    Persisted shape is ``{summary, by_year, equity_curve, errors, skipped_days}``.
    Older or accidental flat stats blobs are accepted as-is.
    """
    if not isinstance(blob, dict):
        return stats_to_dict(None)
    inner = blob.get("summary")
    if isinstance(inner, dict) and "total_trades" in inner:
        return inner
    if "total_trades" in blob:
        return blob
    return stats_to_dict(None)


def summary_list_payload(run: BacktestRun) -> dict[str, Any]:
    blob = json.loads(run.summary)
    return {
        "id": run.id,
        "created_at": run.created_at.isoformat(),
        "name": run.name,
        "symbols": json.loads(run.symbols),
        "start_date": run.start_date.isoformat(),
        "end_date": run.end_date.isoformat(),
        "parameters": json.loads(run.parameters),
        "summary": _unwrap_saved_summary(blob),
    }


def fetch_symbol_bars(
    provider: MarketDataProvider,
    symbols: list[str],
    start_date: date,
    end_date: date,
) -> tuple[dict[str, list[Bar]], list[dict[str, str]]]:
    """Fetch daily bars with warm-up history; isolate per-symbol errors."""
    span = (end_date - start_date).days + 1
    # Extra calendar days for weekends/holidays + 40 warm-up sessions.
    fetch_days = min(span + 80, MAX_HISTORY_YEARS * 366 + 80)
    bars_by_symbol: dict[str, list[Bar]] = {}
    errors: list[dict[str, str]] = []
    for symbol in symbols:
        try:
            bars = provider.get_daily_bars(symbol, days=fetch_days)
            if not bars:
                errors.append({"symbol": symbol, "error": "No daily bars returned"})
                continue
            bars_by_symbol[symbol] = bars
        except MarketDataError as exc:
            errors.append({"symbol": symbol, "error": str(exc)})
        except Exception as exc:  # noqa: BLE001 — isolate unexpected provider issues
            errors.append({"symbol": symbol, "error": str(exc)})
    return bars_by_symbol, errors


def resolve_symbols(
    db: Session,
    symbols: Optional[list[str]],
    use_watchlist: bool,
) -> list[str]:
    resolved: list[str] = []
    if use_watchlist:
        rows = db.scalars(select(WatchlistItem.symbol)).all()
        resolved.extend(str(s).strip().upper() for s in rows if s)
    if symbols:
        resolved.extend(s.strip().upper() for s in symbols if s and s.strip())
    # Dedupe preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for symbol in resolved:
        if symbol and symbol not in seen:
            seen.add(symbol)
            unique.append(symbol)
    if not unique:
        raise ValueError("At least one symbol is required")
    if len(unique) > MAX_SYMBOLS:
        raise ValueError(f"At most {MAX_SYMBOLS} symbols are allowed per run")
    return unique


def execute_and_save(
    db: Session,
    provider: MarketDataProvider,
    *,
    symbols: list[str],
    start_date: date,
    end_date: date,
    params: BacktestParams,
    name: Optional[str] = None,
) -> tuple[BacktestRun, dict[str, Any]]:
    validate_params(params)
    validate_run_limits(symbols, start_date, end_date)
    bars_by_symbol, errors = fetch_symbol_bars(
        provider,
        symbols,
        start_date,
        end_date,
    )
    result = run_backtest(
        bars_by_symbol,
        start_date,
        end_date,
        params,
        errors=errors,
    )
    payload = result_payload(
        result,
        params=params,
        symbols=symbols,
        start_date=start_date,
        end_date=end_date,
        name=name,
    )
    run = BacktestRun(
        name=name,
        parameters=json.dumps(payload["parameters"]),
        symbols=json.dumps(symbols),
        start_date=start_date,
        end_date=end_date,
        summary=json.dumps(
            {
                "summary": payload["summary"],
                "by_year": payload["by_year"],
                "equity_curve": payload["equity_curve"],
                "errors": payload["errors"],
                "skipped_days": payload["skipped_days"],
            }
        ),
        trades=json.dumps(payload["trades"]),
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    payload["id"] = run.id
    payload["created_at"] = run.created_at.isoformat()
    return run, payload


def load_full_run(run: BacktestRun) -> dict[str, Any]:
    summary_blob = json.loads(run.summary)
    return {
        "id": run.id,
        "created_at": run.created_at.isoformat(),
        "name": run.name,
        "parameters": json.loads(run.parameters),
        "symbols": json.loads(run.symbols),
        "start_date": run.start_date.isoformat(),
        "end_date": run.end_date.isoformat(),
        "summary": summary_blob.get("summary", summary_blob),
        "by_year": summary_blob.get("by_year", {}),
        "equity_curve": summary_blob.get("equity_curve", []),
        "errors": summary_blob.get("errors", []),
        "skipped_days": summary_blob.get("skipped_days", 0),
        "trades": json.loads(run.trades),
    }


def list_runs(db: Session) -> list[BacktestRun]:
    stmt = select(BacktestRun).order_by(
        BacktestRun.created_at.desc(),
        BacktestRun.id.desc(),
    )
    return list(db.scalars(stmt).all())


def get_run(db: Session, run_id: int) -> Optional[BacktestRun]:
    return db.get(BacktestRun, run_id)


def delete_run(db: Session, run_id: int) -> bool:
    run = db.get(BacktestRun, run_id)
    if run is None:
        return False
    db.delete(run)
    db.commit()
    return True


def params_from_request(body: dict[str, Any]) -> BacktestParams:
    def d(key: str, default: str) -> Decimal:
        raw = body.get(key, default)
        return Decimal(str(raw))

    return BacktestParams(
        min_gap_percent=d("min_gap_percent", "2"),
        min_relative_volume=d("min_relative_volume", "2"),
        min_price=d("min_price", "5"),
        min_avg_volume=d("min_avg_volume", "500000"),
        entry_rule=str(body.get("entry_rule", "break_prev_high")),
        stop_rule=str(body.get("stop_rule", "fixed_percent")),
        stop_percent=d("stop_percent", "2"),
        target_r=d("target_r", "2"),
        cost_per_share=d("cost_per_share", "0.02"),
        risk_per_trade_percent=d("risk_per_trade_percent", "1"),
        starting_account=d("starting_account", "10000"),
    )
