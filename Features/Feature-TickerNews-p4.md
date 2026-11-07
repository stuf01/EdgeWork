# Feature: Ticker News Feed

**Source prompt:** `Prompt-4.txt`  
**Status:** Implemented

## Summary

Adds Alpaca news to ticker detail and lightweight news flags on scanner results. Headlines/summaries/links only (no article bodies or images). News failures never break the scanner.

## Requirements (from prompt)

- Provider `get_news(symbol, limit)` → `NewsItem` dataclass
- 5-minute per-symbol cache
- `GET /api/tickers/{symbol}/news` with `count_last_24h` and `has_recent_news`
- Scanner enrichment for filtered symbols (batched; null on failure)
- News panel on ticker page; sortable News column on scanner

## What was built

### Backend

| Path | Role |
| --- | --- |
| `backend/app/news.py` | `count_last_24h` / `has_recent_news` helpers |
| `backend/app/providers/base.py` | `NewsItem`, provider method |
| `backend/app/providers/alpaca.py` | `/v1beta1/news` client + cache |
| `backend/app/main.py` | News endpoint; scanner news enrichment |

**Endpoints**

- `GET /api/tickers/{symbol}/news`

### Frontend

| Path | Role |
| --- | --- |
| `frontend/src/pages/TickerDetailPage.tsx` | News panel (24h status, relative time, CT hover) |
| `frontend/src/pages/ScannerPage.tsx` | News column (count / green-gray / dash) |
| `frontend/src/api.ts` | News types + client |

Links open in a new tab with `rel="noopener noreferrer"`.

### Tests

- Unit: 24h window counting
- API: normal / empty / provider failure via fake provider
- Scanner continues when news fails
