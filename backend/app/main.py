"""FastAPI application entrypoint for the trade planner API."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app import backtest_service, crud
from app.backtest import BacktestParams
from app.checklist import ChecklistRuleSpec, evaluate, score
from app.checklist_context import build_checklist_context
from app.crud import (
    ChecklistValidationError,
    DuplicateWatchlistSymbolError,
    PlanUpdateError,
)
from app.database import SessionLocal, get_db
from app.journal import (
    compute_stats,
    cumulative_pnl_series,
    stats_by_checklist_score,
    stats_by_tag,
)
from app.levels import key_levels, sma, vwap
from app.news import news_activity
from app.planner import calculate_plan
from app.providers import get_provider
from app.providers.base import MarketDataError, MarketDataProvider
from app.scanner import avg_daily_volume, gap_percent, relative_volume
from app.schemas import (
    BacktestCreateRequest,
    CalculateRequest,
    CalculateResponse,
    ChecklistEvaluateRequest,
    ChecklistEvaluateResponse,
    ChecklistResponse,
    ChecklistRuleResultResponse,
    ChecklistScoreBreakdown,
    ChecklistScoreGroupResponse,
    ChecklistUpsertRequest,
    CreatePlanRequest,
    CumulativePnlPoint,
    IntradayBarResponse,
    JournalStatsBlock,
    JournalStatsResponse,
    KeyLevelsResponse,
    NewsItemResponse,
    ScannerErrorItem,
    ScannerExcludedItem,
    ScannerResponse,
    ScannerResultItem,
    TagStatsBlock,
    TickerDetailResponse,
    TickerNewsResponse,
    TradePlanResponse,
    UpdatePlanRequest,
    WatchlistCreateRequest,
    WatchlistItemResponse,
)
from app.timeframes import (
    ALLOWED_TIMEFRAMES,
    DEFAULT_TIMEFRAME,
    is_intraday_timeframe,
    is_valid_timeframe,
)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    db = SessionLocal()
    try:
        crud.ensure_default_checklist(db)
    except Exception:
        # Tables may not exist yet (pre-migration); seed also runs on GET.
        db.rollback()
    finally:
        db.close()
    yield


app = FastAPI(title="Trade Planner API", version="0.6.0", lifespan=lifespan)


def _plan_response(plan) -> TradePlanResponse:
    extras = crud.enrich_plan_response_fields(plan)
    return TradePlanResponse.model_validate(
        {**TradePlanResponse.model_validate(plan).model_dump(), **extras}
    )


def _stats_block(stats) -> JournalStatsBlock:
    return JournalStatsBlock(
        total_trades=stats.total_trades,
        wins=stats.wins,
        losses=stats.losses,
        win_rate=stats.win_rate,
        avg_win=stats.avg_win,
        avg_loss=stats.avg_loss,
        avg_r=stats.avg_r,
        expectancy_r=stats.expectancy_r,
        total_pnl=stats.total_pnl,
        best_trade=stats.best_trade,
        worst_trade=stats.worst_trade,
        max_drawdown=stats.max_drawdown,
    )


def _format_actual(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, Decimal):
        return format(value, "f")
    return str(value)


def _rules_to_specs(checklist) -> list[ChecklistRuleSpec]:
    return [
        ChecklistRuleSpec(
            label=rule.label,
            rule_type=rule.rule_type,
            operator=rule.operator,
            threshold=rule.threshold,
            required=rule.required,
        )
        for rule in sorted(checklist.rules, key=lambda r: r.position)
    ]


def _evaluate_checklist_payload(checklist, context: dict) -> ChecklistEvaluateResponse:
    results = evaluate(_rules_to_specs(checklist), context)
    scored = score(results)
    return ChecklistEvaluateResponse(
        checklist_id=checklist.id,
        checklist_name=checklist.name,
        results=[
            ChecklistRuleResultResponse(
                label=item.label,
                passed=item.passed,
                actual=_format_actual(item.actual),
                threshold=(
                    format(item.threshold, "f") if item.threshold is not None else None
                ),
                required=item.required,
                rule_type=item.rule_type,
                operator=item.operator,
            )
            for item in results
        ],
        score=scored.score,
        unknown_count=scored.unknown_count,
        required_failed=scored.required_failed,
        verdict=scored.verdict,
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:9001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """Return 422 with a readable validation message."""
    errors = exc.errors()
    messages = []
    for err in errors:
        loc = " -> ".join(str(part) for part in err.get("loc", ()) if part != "body")
        msg = err.get("msg", "Invalid value")
        messages.append(f"{loc}: {msg}" if loc else msg)
    detail = "; ".join(messages) if messages else "Validation error"
    return JSONResponse(status_code=422, content={"detail": detail})


def get_market_data_provider() -> MarketDataProvider:
    """FastAPI dependency for the market data provider."""
    try:
        return get_provider()
    except MarketDataError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/api/plans/calculate", response_model=CalculateResponse)
def calculate_only(body: CalculateRequest) -> CalculateResponse:
    """Calculate a trade plan without saving it."""
    try:
        result = calculate_plan(
            body.account_size,
            body.risk_percent,
            body.entry,
            body.stop,
            body.target,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return CalculateResponse(**result)


@app.post("/api/plans", response_model=TradePlanResponse, status_code=201)
def create_plan(
    body: CreatePlanRequest,
    db: Session = Depends(get_db),
    provider: MarketDataProvider = Depends(get_market_data_provider),
) -> TradePlanResponse:
    """Calculate and persist a trade plan, optionally scoring a checklist."""
    checklist_score = None
    checklist_id = body.checklist_id
    if checklist_id is not None:
        checklist = crud.get_checklist(db, checklist_id)
        if checklist is None:
            raise HTTPException(
                status_code=404,
                detail=f"Checklist {checklist_id} not found",
            )
        context = build_checklist_context(
            provider,
            symbol=body.symbol,
            entry=body.entry,
            stop=body.stop,
            target=body.target,
        )
        checklist_score = _evaluate_checklist_payload(checklist, context).score
    try:
        plan = crud.create_plan(
            db,
            symbol=body.symbol,
            account_size=body.account_size,
            risk_percent=body.risk_percent,
            entry=body.entry,
            stop=body.stop,
            target=body.target,
            notes=body.notes,
            setup_tag=body.setup_tag,
            is_paper=body.is_paper,
            checklist_id=checklist_id,
            checklist_score=checklist_score,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _plan_response(plan)


@app.get("/api/plans", response_model=list[TradePlanResponse])
def get_plans(db: Session = Depends(get_db)) -> list[TradePlanResponse]:
    """List saved plans, newest first."""
    plans = crud.list_plans(db)
    return [_plan_response(plan) for plan in plans]


@app.patch("/api/plans/{plan_id}", response_model=TradePlanResponse)
def patch_plan(
    plan_id: int,
    body: UpdatePlanRequest,
    db: Session = Depends(get_db),
) -> TradePlanResponse:
    """Update journal fields and status transitions for a plan."""
    plan = crud.get_plan(db, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail=f"Plan {plan_id} not found")
    try:
        updated = crud.update_plan(
            db,
            plan,
            status=body.status,
            notes=body.notes,
            setup_tag=body.setup_tag,
            is_paper=body.is_paper,
            actual_entry=body.actual_entry,
            actual_exit=body.actual_exit,
            shares_traded=body.shares_traded,
            exit_reason=body.exit_reason,
            lessons=body.lessons,
            fields_set=set(body.model_fields_set),
        )
    except PlanUpdateError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _plan_response(updated)


@app.delete("/api/plans/{plan_id}", status_code=204)
def remove_plan(plan_id: int, db: Session = Depends(get_db)) -> None:
    """Delete a saved plan by id."""
    deleted = crud.delete_plan(db, plan_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Plan {plan_id} not found")


@app.get("/api/journal/stats", response_model=JournalStatsResponse)
def journal_stats(
    is_paper: Optional[bool] = Query(default=None),
    setup_tag: Optional[str] = Query(default=None),
    from_: Optional[datetime] = Query(default=None, alias="from"),
    to: Optional[datetime] = Query(default=None),
    db: Session = Depends(get_db),
) -> JournalStatsResponse:
    """Overall journal stats, by-tag breakdown, and cumulative P&L series."""
    plans = crud.list_closed_trades(
        db,
        is_paper=is_paper,
        setup_tag=setup_tag,
        from_dt=from_,
        to_dt=to,
    )
    closed = [crud.plan_to_closed_trade(plan) for plan in plans]
    overall = compute_stats(closed)
    by_tag = stats_by_tag(closed)
    series = cumulative_pnl_series(closed)
    by_score = stats_by_checklist_score(closed)
    return JournalStatsResponse(
        overall=_stats_block(overall),
        by_tag=[
            TagStatsBlock(tag=tag, **_stats_block(stats).model_dump())
            for tag, stats in by_tag.items()
        ],
        cumulative_pnl=[
            CumulativePnlPoint(closed_at=ts, cumulative_pnl=value)
            for ts, value in series
        ],
        by_checklist_score=ChecklistScoreBreakdown(
            met=ChecklistScoreGroupResponse(
                count=by_score["met"].count,
                win_rate=by_score["met"].win_rate,
                expectancy_r=by_score["met"].expectancy_r,
            ),
            below=ChecklistScoreGroupResponse(
                count=by_score["below"].count,
                win_rate=by_score["below"].win_rate,
                expectancy_r=by_score["below"].expectancy_r,
            ),
        ),
    )


@app.get("/api/checklists", response_model=list[ChecklistResponse])
def get_checklists(db: Session = Depends(get_db)) -> list[ChecklistResponse]:
    """List all checklists with rules."""
    crud.ensure_default_checklist(db)
    items = crud.list_checklists(db)
    return [ChecklistResponse.model_validate(item) for item in items]


@app.post("/api/checklists", response_model=ChecklistResponse, status_code=201)
def post_checklist(
    body: ChecklistUpsertRequest,
    db: Session = Depends(get_db),
) -> ChecklistResponse:
    """Create a checklist with rules."""
    try:
        created = crud.create_checklist(
            db,
            name=body.name,
            description=body.description,
            rules=[rule.model_dump() for rule in body.rules],
        )
    except ChecklistValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ChecklistResponse.model_validate(created)


@app.put("/api/checklists/{checklist_id}", response_model=ChecklistResponse)
def put_checklist(
    checklist_id: int,
    body: ChecklistUpsertRequest,
    db: Session = Depends(get_db),
) -> ChecklistResponse:
    """Replace a checklist name/description/rules."""
    checklist = crud.get_checklist(db, checklist_id)
    if checklist is None:
        raise HTTPException(
            status_code=404,
            detail=f"Checklist {checklist_id} not found",
        )
    try:
        updated = crud.replace_checklist(
            db,
            checklist,
            name=body.name,
            description=body.description,
            rules=[rule.model_dump() for rule in body.rules],
        )
    except ChecklistValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ChecklistResponse.model_validate(updated)


@app.delete("/api/checklists/{checklist_id}", status_code=204)
def remove_checklist(checklist_id: int, db: Session = Depends(get_db)) -> None:
    """Delete a checklist and its rules."""
    deleted = crud.delete_checklist(db, checklist_id)
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail=f"Checklist {checklist_id} not found",
        )


@app.post(
    "/api/checklists/{checklist_id}/evaluate",
    response_model=ChecklistEvaluateResponse,
)
def evaluate_checklist(
    checklist_id: int,
    body: ChecklistEvaluateRequest,
    db: Session = Depends(get_db),
    provider: MarketDataProvider = Depends(get_market_data_provider),
) -> ChecklistEvaluateResponse:
    """Evaluate a checklist against live market context for a trade idea."""
    checklist = crud.get_checklist(db, checklist_id)
    if checklist is None:
        raise HTTPException(
            status_code=404,
            detail=f"Checklist {checklist_id} not found",
        )
    context = build_checklist_context(
        provider,
        symbol=body.symbol,
        entry=body.entry,
        stop=body.stop,
        target=body.target,
    )
    return _evaluate_checklist_payload(checklist, context)


@app.get("/api/watchlist", response_model=list[WatchlistItemResponse])
def get_watchlist(db: Session = Depends(get_db)) -> list[WatchlistItemResponse]:
    """List watchlist symbols, newest first."""
    items = crud.list_watchlist(db)
    return [WatchlistItemResponse.model_validate(item) for item in items]


@app.post("/api/watchlist", response_model=WatchlistItemResponse, status_code=201)
def create_watchlist_item(
    body: WatchlistCreateRequest,
    db: Session = Depends(get_db),
) -> WatchlistItemResponse:
    """Add a symbol to the watchlist."""
    try:
        item = crud.add_watchlist_item(db, symbol=body.symbol, notes=body.notes)
    except DuplicateWatchlistSymbolError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return WatchlistItemResponse.model_validate(item)


@app.delete("/api/watchlist/{symbol}", status_code=204)
def remove_watchlist_item(symbol: str, db: Session = Depends(get_db)) -> None:
    """Remove a symbol from the watchlist."""
    deleted = crud.delete_watchlist_item(db, symbol)
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail=f"Symbol {symbol.upper()} is not on the watchlist",
        )


@app.get("/api/scanner", response_model=ScannerResponse)
def run_scanner(
    min_price: Optional[Decimal] = Query(default=None, gt=0),
    max_price: Optional[Decimal] = Query(default=None, gt=0),
    min_gap_percent: Optional[Decimal] = Query(default=None, ge=0),
    min_relative_volume: Optional[Decimal] = Query(default=None, gt=0),
    min_avg_volume: Optional[Decimal] = Query(default=None, gt=0),
    db: Session = Depends(get_db),
    provider: MarketDataProvider = Depends(get_market_data_provider),
) -> ScannerResponse:
    """Scan every watchlist symbol and return filtered gap/volume metrics."""
    items = crud.list_watchlist(db)
    symbols = [item.symbol for item in items]
    if not symbols:
        return ScannerResponse(scanned=0, results=[], excluded=[], errors=[])

    errors: list[ScannerErrorItem] = []
    excluded: list[ScannerExcludedItem] = []
    try:
        snapshots = provider.get_snapshots(symbols)
    except MarketDataError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    today = datetime.now(timezone.utc).date()
    results: list[ScannerResultItem] = []

    for symbol in symbols:
        snapshot = snapshots.get(symbol)
        if snapshot is None:
            errors.append(
                ScannerErrorItem(symbol=symbol, error="No snapshot data available")
            )
            continue
        try:
            bars = provider.get_daily_bars(symbol, days=30)
            gap = gap_percent(snapshot.today_open, snapshot.prev_close)
            avg_vol = avg_daily_volume(bars, exclude_date=today, lookback=20)
            rel_vol = relative_volume(snapshot.today_volume, avg_vol)
            if gap is None or avg_vol is None or rel_vol is None:
                errors.append(
                    ScannerErrorItem(
                        symbol=symbol,
                        error="Insufficient data to compute gap/volume metrics",
                    )
                )
                continue

            row = ScannerResultItem(
                symbol=symbol,
                last_price=snapshot.last_price,
                gap_percent=gap,
                relative_volume=rel_vol,
                avg_daily_volume=avg_vol,
                today_volume=snapshot.today_volume,
            )
            reason = _filter_reason(
                row,
                min_price=min_price,
                max_price=max_price,
                min_gap_percent=min_gap_percent,
                min_relative_volume=min_relative_volume,
                min_avg_volume=min_avg_volume,
            )
            if reason is None:
                results.append(row)
            else:
                excluded.append(
                    ScannerExcludedItem(**row.model_dump(), reason=reason)
                )
        except MarketDataError as exc:
            errors.append(ScannerErrorItem(symbol=symbol, error=str(exc)))
        except Exception as exc:  # noqa: BLE001 — isolate per-symbol failures
            errors.append(
                ScannerErrorItem(symbol=symbol, error=f"Unexpected error: {exc}")
            )

    # Enrich passing symbols with recent-news flags; never fail the scan.
    if results:
        try:
            news_map = provider.get_news_for_symbols(
                [row.symbol for row in results],
                limit=10,
            )
            enriched: list[ScannerResultItem] = []
            for row in results:
                items = news_map.get(row.symbol, [])
                count, has_recent = news_activity(items)
                enriched.append(
                    row.model_copy(
                        update={
                            "count_last_24h": count,
                            "has_recent_news": has_recent,
                        }
                    )
                )
            results = enriched
        except MarketDataError:
            pass
        except Exception:  # noqa: BLE001 — news is optional for scanner
            pass

    results.sort(key=lambda row: abs(row.gap_percent), reverse=True)
    excluded.sort(key=lambda row: abs(row.gap_percent), reverse=True)
    return ScannerResponse(
        scanned=len(symbols),
        results=results,
        excluded=excluded,
        errors=errors,
    )


def _filter_reason(
    row: ScannerResultItem,
    *,
    min_price: Optional[Decimal],
    max_price: Optional[Decimal],
    min_gap_percent: Optional[Decimal],
    min_relative_volume: Optional[Decimal],
    min_avg_volume: Optional[Decimal],
) -> Optional[str]:
    """Return a human-readable filter failure reason, or None if the row passes."""
    if min_price is not None and row.last_price < min_price:
        return f"last price {row.last_price} below min_price {min_price}"
    if max_price is not None and row.last_price > max_price:
        return f"last price {row.last_price} above max_price {max_price}"
    if min_gap_percent is not None and abs(row.gap_percent) < min_gap_percent:
        return (
            f"|gap| {abs(row.gap_percent)} below min_gap_percent {min_gap_percent}"
        )
    if (
        min_relative_volume is not None
        and row.relative_volume < min_relative_volume
    ):
        return (
            f"relative volume {row.relative_volume} below "
            f"min_relative_volume {min_relative_volume}"
        )
    if min_avg_volume is not None and row.avg_daily_volume < min_avg_volume:
        return (
            f"avg volume {row.avg_daily_volume} below "
            f"min_avg_volume {min_avg_volume}"
        )
    return None


@app.get("/api/tickers/{symbol}/detail", response_model=TickerDetailResponse)
def ticker_detail(
    symbol: str,
    timeframe: str = Query(default=DEFAULT_TIMEFRAME),
    refresh: bool = Query(default=False),
    provider: MarketDataProvider = Depends(get_market_data_provider),
) -> TickerDetailResponse:
    """Return chart bars, optional VWAP, and key levels for a symbol."""
    cleaned = symbol.strip().upper()
    if not cleaned:
        raise HTTPException(status_code=404, detail="Symbol is required")

    if not is_valid_timeframe(timeframe):
        allowed = ", ".join(ALLOWED_TIMEFRAMES.keys())
        raise HTTPException(
            status_code=422,
            detail=(
                f"Invalid timeframe '{timeframe}'. "
                f"Allowed values: {allowed}."
            ),
        )

    if refresh:
        from app.providers.cache import (
            bars_cache,
            chart_bars_cache,
            snapshot_cache,
        )

        chart_bars_cache.delete((cleaned, timeframe))
        bars_cache.delete((cleaned, 60))
        snapshot_cache.delete(cleaned)

    try:
        snapshots = provider.get_snapshots([cleaned])
    except MarketDataError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    snapshot = snapshots.get(cleaned)
    if snapshot is None:
        raise HTTPException(
            status_code=404,
            detail=f"No market data found for symbol {cleaned}",
        )

    try:
        chart_bars = provider.get_bars(cleaned, timeframe=timeframe)
        daily = provider.get_daily_bars(cleaned, days=60)
    except MarketDataError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if not chart_bars:
        raise HTTPException(
            status_code=404,
            detail=f"No bars available for symbol {cleaned} ({timeframe})",
        )

    chart_bars = sorted(chart_bars, key=lambda bar: bar.timestamp)
    vwap_series = (
        vwap(chart_bars) if is_intraday_timeframe(timeframe) else []
    )

    today = datetime.now(timezone.utc).date()
    levels = key_levels(daily, snapshot.today_open, exclude_date=today)
    gap = gap_percent(snapshot.today_open, snapshot.prev_close)

    return TickerDetailResponse(
        symbol=cleaned,
        timeframe=timeframe,
        last_price=snapshot.last_price,
        bars=[
            IntradayBarResponse(
                timestamp=bar.timestamp,
                open=bar.open,
                high=bar.high,
                low=bar.low,
                close=bar.close,
                volume=bar.volume,
            )
            for bar in chart_bars
        ],
        vwap=vwap_series,
        levels=KeyLevelsResponse(
            prev_day_high=levels.prev_day_high,
            prev_day_low=levels.prev_day_low,
            prev_day_close=levels.prev_day_close,
            today_open=levels.today_open,
        ),
        sma_20=sma(daily, 20),
        sma_50=sma(daily, 50),
        gap_percent=gap,
    )


@app.get("/api/tickers/{symbol}/news", response_model=TickerNewsResponse)
def ticker_news(
    symbol: str,
    limit: int = Query(default=10, ge=1, le=50),
    provider: MarketDataProvider = Depends(get_market_data_provider),
) -> TickerNewsResponse:
    """Return recent headline news for a symbol."""
    cleaned = symbol.strip().upper()
    if not cleaned:
        raise HTTPException(status_code=404, detail="Symbol is required")

    try:
        items = provider.get_news(cleaned, limit=limit)
    except MarketDataError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    count, has_recent = news_activity(items)
    return TickerNewsResponse(
        symbol=cleaned,
        items=[
            NewsItemResponse(
                id=item.id,
                headline=item.headline,
                summary=item.summary,
                source=item.source,
                url=item.url,
                created_at=item.created_at,
                symbols=list(item.symbols),
            )
            for item in items
        ],
        count_last_24h=count,
        has_recent_news=has_recent,
    )


@app.post("/api/backtests", status_code=201)
def create_backtest(
    body: BacktestCreateRequest,
    db: Session = Depends(get_db),
    provider: MarketDataProvider = Depends(get_market_data_provider),
) -> dict:
    """Run a gap-breakout backtest, persist it, and return the full result."""
    try:
        symbols = backtest_service.resolve_symbols(
            db,
            body.symbols,
            body.use_watchlist,
        )
        params = BacktestParams(
            min_gap_percent=body.min_gap_percent,
            min_relative_volume=body.min_relative_volume,
            min_price=body.min_price,
            min_avg_volume=body.min_avg_volume,
            entry_rule=body.entry_rule,
            stop_rule=body.stop_rule,
            stop_percent=body.stop_percent,
            target_r=body.target_r,
            cost_per_share=body.cost_per_share,
            risk_per_trade_percent=body.risk_per_trade_percent,
            starting_account=body.starting_account,
        )
        _, payload = backtest_service.execute_and_save(
            db,
            provider,
            symbols=symbols,
            start_date=body.start_date,
            end_date=body.end_date,
            params=params,
            name=body.name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return payload


@app.get("/api/backtests")
def list_backtests(db: Session = Depends(get_db)) -> list[dict]:
    """List saved backtests, newest first (summaries only)."""
    runs = backtest_service.list_runs(db)
    return [backtest_service.summary_list_payload(run) for run in runs]


@app.get("/api/backtests/{run_id}")
def get_backtest(run_id: int, db: Session = Depends(get_db)) -> dict:
    """Return a full saved backtest result."""
    run = backtest_service.get_run(db, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Backtest {run_id} not found")
    return backtest_service.load_full_run(run)


@app.delete("/api/backtests/{run_id}", status_code=204)
def delete_backtest(run_id: int, db: Session = Depends(get_db)) -> None:
    """Delete a saved backtest run."""
    deleted = backtest_service.delete_run(db, run_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Backtest {run_id} not found")
