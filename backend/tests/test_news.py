"""Unit tests for news activity helpers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.news import news_activity
from app.providers.base import NewsItem


def _item(hours_ago: float, item_id: str = "1") -> NewsItem:
    return NewsItem(
        id=item_id,
        headline="Headline",
        summary="Summary",
        source="Wire",
        url="https://example.com",
        created_at=datetime.now(timezone.utc) - timedelta(hours=hours_ago),
        symbols=("TEST",),
    )


def test_news_activity_counts_only_last_24h() -> None:
    items = [_item(1, "recent"), _item(30, "old"), _item(5, "also-recent")]
    count, has_recent = news_activity(items)
    assert count == 2
    assert has_recent is True


def test_news_activity_none_in_window() -> None:
    items = [_item(25, "old1"), _item(48, "old2")]
    count, has_recent = news_activity(items)
    assert count == 0
    assert has_recent is False


def test_news_activity_empty() -> None:
    count, has_recent = news_activity([])
    assert count == 0
    assert has_recent is False
