"""News helpers (pure counting / windowing)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Sequence

from app.providers.base import NewsItem


def news_activity(
    items: Sequence[NewsItem],
    *,
    now: datetime | None = None,
    window: timedelta = timedelta(hours=24),
) -> tuple[int, bool]:
    """Return (count_last_window, has_recent_news) for UTC timestamps."""
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    cutoff = current - window
    count = 0
    for item in items:
        created = item.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        if created >= cutoff:
            count += 1
    return count, count > 0
