"""Optional in-process scheduler for agent cycles and order sync."""

from __future__ import annotations

from typing import Any

from app.agents.market_hours import is_cycle_window
from app.database import SessionLocal

_scheduler: Any = None


def start_scheduler() -> None:
    """Start APScheduler jobs if available and not already running."""
    global _scheduler
    if _scheduler is not None:
        return
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
    except ImportError:
        return

    scheduler = BackgroundScheduler(timezone="America/New_York")
    scheduler.add_job(
        _scheduled_cycle,
        "interval",
        minutes=1,
        id="agent_cycle_tick",
        replace_existing=True,
    )
    scheduler.add_job(
        _scheduled_sync,
        "interval",
        minutes=1,
        id="agent_order_sync",
        replace_existing=True,
    )
    scheduler.start()
    _scheduler = scheduler


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is None:
        return
    _scheduler.shutdown(wait=False)
    _scheduler = None


def _scheduled_cycle() -> None:
    from app.agents.cycle import run_cycle
    from app.agents.paper_client import AlpacaPaperClient, PaperTradingError
    from app.agents.service import get_or_create_settings
    from app.providers import get_earnings_provider, get_provider

    db = SessionLocal()
    try:
        settings = get_or_create_settings(db)
        if not settings.scheduler_enabled or not settings.enabled:
            return
        if settings.kill_switch:
            return
        if not is_cycle_window():
            return
        # Throttle to cycle_interval_minutes using last SYSTEM cycle event would
        # be ideal; for simplicity run when window open and interval elapsed
        # is handled by checking minute modulo.
        from datetime import datetime
        from zoneinfo import ZoneInfo

        now = datetime.now(ZoneInfo("America/New_York"))
        if now.minute % max(1, settings.cycle_interval_minutes) != 0:
            return
        try:
            broker = AlpacaPaperClient()
        except PaperTradingError:
            return
        run_cycle(
            db,
            get_provider(),
            broker,
            earnings_provider=get_earnings_provider(),
        )
    finally:
        db.close()


def _scheduled_sync() -> None:
    from app.agents.sync import sync_open_orders
    from app.agents.paper_client import AlpacaPaperClient, PaperTradingError
    from app.agents.service import get_or_create_settings

    db = SessionLocal()
    try:
        settings = get_or_create_settings(db)
        if not settings.scheduler_enabled:
            return
        try:
            broker = AlpacaPaperClient()
        except PaperTradingError:
            return
        sync_open_orders(db, broker)
    finally:
        db.close()
