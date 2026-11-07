# Feature: Ticker Detail Page & Candlestick Chart

**Source prompt:** `Prompt-3.txt`  
**Status:** Implemented

## Summary

Ticker detail route with intraday candlesticks (lightweight-charts), volume, VWAP, and key levels (prior day high/low/close, today’s open, SMA20/50, gap %). Scanner symbols link into the detail page; levels are click-to-copy for pasting into the planner.

## Requirements (from prompt)

- Provider: `get_intraday_bars` (Alpaca `/v2/stocks/bars`, IEX, Decimal prices, 30s cache)
- Pure `levels.py`: VWAP (resets per NY session day), `key_levels`, `sma`
- `GET /api/tickers/{symbol}/detail`
- Chart: candles + volume + VWAP + horizontal PDH/PDL/Open lines
- Route `/ticker/:symbol` with summary panel and “Plan trade”

## What was built

### Backend

| Path | Role |
| --- | --- |
| `backend/app/levels.py` | VWAP, key levels, SMA |
| `backend/app/providers/base.py` | Intraday bar types / provider methods |
| `backend/app/providers/alpaca.py` | Bars fetch + cache |
| `backend/app/main.py` | `GET /api/tickers/{symbol}/detail` |

Detail payload includes: symbol, last price, bars, VWAP series, key levels, SMA20/50, gap %.

### Frontend

| Path | Role |
| --- | --- |
| `frontend/src/pages/TickerDetailPage.tsx` | Detail layout, summary, plan CTA |
| `frontend/src/components/Chart.tsx` | Candles, volume, VWAP, level lines |
| `frontend/src/pages/ScannerPage.tsx` | Symbol → `/ticker/:symbol` links |
| `frontend/src/api.ts` | `getTickerDetail` types |

### Tests

- Unit: VWAP hand example, SMA insufficient bars → `None`, key levels
- API: detail via fake provider; unknown symbol → 404
