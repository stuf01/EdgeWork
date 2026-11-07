# Feature: Multi-Timeframe Charts

**Source prompt:** `Prompt-3b.txt`  
**Status:** Implemented

## Summary

Extends ticker detail so the chart can switch among 1m / 5m / 15m / 1h / 1D without a full page reload. Lookbacks and caches are per timeframe; VWAP is omitted on daily; key levels and SMAs always come from daily bars.

## Requirements (from prompt)

- Bars API accepts: `1Min`, `5Min`, `15Min`, `1Hour`, `1Day` with sensible lookbacks and bar caps
- Query param `timeframe` on detail (default `5Min`); invalid → 422
- VWAP only for intraday; cache keyed by symbol + timeframe
- UI timeframe buttons; persist last choice in `localStorage`
- Axis formatting in America/Chicago (intraday hours vs daily dates)

## What was built

### Backend

| Path | Role |
| --- | --- |
| `backend/app/timeframes.py` | Allowed frames, lookbacks, validation helpers |
| `backend/app/providers/alpaca.py` | Per-timeframe bar fetch + cache keys |
| `backend/app/providers/cache.py` | Separate TTLs (30s intraday / 6h daily) |
| `backend/app/main.py` | `timeframe` query on `/api/tickers/{symbol}/detail` |

Default lookbacks (as implemented): 1Min→2d, 5Min→5d, 15Min→10d, 1Hour→30d, 1Day→1y.

### Frontend

| Path | Role |
| --- | --- |
| `frontend/src/pages/TickerDetailPage.tsx` | Timeframe button row, chart-only loading |
| `frontend/src/lib/planStorage.ts` / related storage helpers | Persist `edgework.chartTimeframe` |
| `frontend/src/components/Chart.tsx` | Hide VWAP on 1D; CT time axis |

### Tests

- Invalid timeframe rejected
- VWAP absent for `1Day`, present for `5Min`
- Cache keeps timeframes separate (fake provider)
