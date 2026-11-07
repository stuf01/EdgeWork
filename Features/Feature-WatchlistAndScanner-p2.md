# Feature: Market Data Provider, Watchlist & Scanner

**Source prompt:** `Prompt-2.txt`  
**Status:** Implemented

## Summary

Adds a swappable market-data provider (Alpaca IEX), a per-user watchlist, and a watchlist-only scanner with gap %, relative volume, and average volume filters. Scanner symbols that fail filters are listed separately; data errors do not fail the whole scan.

## Requirements (from prompt)

- `MarketDataProvider` ABC: `get_snapshots`, `get_daily_bars`
- Alpaca REST via `httpx`, credentials from `.env`, batching, 429/error handling
- In-memory TTL cache (30s snapshots, 6h daily bars)
- `WatchlistItem` model + CRUD endpoints
- Pure scanner math in `scanner.py`
- Scanner page with filters, sortable results, “Plan trade” deep-link to Planner

## What was built

### Backend

| Path | Role |
| --- | --- |
| `backend/app/providers/base.py` | Provider ABC + `Snapshot` / `Bar` dataclasses |
| `backend/app/providers/alpaca.py` | Alpaca IEX implementation |
| `backend/app/providers/cache.py` | TTL cache |
| `backend/app/providers/__init__.py` | `get_provider()` singleton |
| `backend/app/scanner.py` | `gap_percent`, `avg_daily_volume`, `relative_volume` |
| `backend/app/models.py` | `WatchlistItem` |
| `backend/alembic/versions/2d375de1169c_create_watchlist_items_table.py` | Migration |
| `backend/.env.example` | `ALPACA_API_KEY`, `ALPACA_API_SECRET`, `ALPACA_DATA_URL` |

**Endpoints**

- `GET/POST /api/watchlist`, `DELETE /api/watchlist/{symbol}`
- `GET /api/scanner` — filters: `min_price`, `max_price`, `min_gap_percent`, `min_relative_volume`, `min_avg_volume`

### Frontend

| Path | Role |
| --- | --- |
| `frontend/src/pages/ScannerPage.tsx` | Watchlist panel, filters, results / excluded / errors |
| `frontend/src/App.tsx` | Nav: Planner ↔ Scanner (later pages added) |
| `frontend/src/api.ts` | Watchlist + scanner typed calls |

Default filter defaults: min price 5, max 500, min gap 2, min RVol 1.5, min avg volume 500000.

### Tests

- Unit tests for gap / avg volume / relative volume (including divide-by-zero)
- API tests with `FakeProvider` (no network): filters, duplicate watchlist 409, bad symbol → `errors`

## Env

```text
ALPACA_API_KEY=...
ALPACA_API_SECRET=...
ALPACA_DATA_URL=https://data.alpaca.markets
```
