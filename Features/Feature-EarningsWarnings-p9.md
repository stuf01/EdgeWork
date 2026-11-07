# Feature: Earnings Dates & Warnings

**Source prompt:** `Prompt-9.txt`  
**Status:** Implemented

## Summary

Earnings calendar via Finnhub with risk badges on scanner/ticker/plan-on-chart, a `days_to_earnings` checklist rule (seeded into Breakout basics), and optional backtester skip window near earnings.

## Requirements (from prompt)

### Backend

- `EarningsProvider` ABC + `EarningsEvent` (`before_open` / `after_close` / `unknown`)
- `backend/app/providers/finnhub.py` using Finnhub earnings calendar; `FINNHUB_API_KEY` in `.env` / `.env.example`
- 12h per-symbol cache; sequential fetches with short delay; one-symbol failure does not fail the batch
- Pure `earnings.py`: `next_earnings`, `days_until`, `risk_level` (`today_or_tomorrow` / `this_week` / `later` / `none`)
- `GET /api/tickers/{symbol}/earnings`
- Enrich scanner + ticker detail with `next_earnings_date`, `days_until_earnings`, `earnings_risk` (null on failure)
- Checklist rule `days_to_earnings`; add as required (threshold 2) to “Breakout basics” if missing
- Backtest param `skip_earnings_days` (default 0); report skipped count or that earnings data was unavailable

### Frontend

- Scanner “Earnings” column (red 0–1d, amber ≤7d, dash none/unknown), sortable
- Ticker / on-chart planner: banner when earnings are within 7 days (red for 0–1)
- Backtest form “skip trades near earnings” input
- Typed `api.ts` updates

## What was built

### Backend

| Path | Role |
| --- | --- |
| `backend/app/earnings.py` | Pure helpers |
| `backend/app/providers/base.py` | `EarningsEvent`, `EarningsProvider`, errors |
| `backend/app/providers/finnhub.py` | Finnhub REST + cache |
| `backend/app/providers/null_earnings.py` | Empty provider when no API key |
| `backend/app/providers/cache.py` | 12h `earnings_cache` |
| `backend/app/checklist.py` | `days_to_earnings` registry + seed rule |
| `backend/app/checklist_context.py` | Context enrichment |
| `backend/app/crud.py` | Ensure Breakout basics rule on existing DBs |
| `backend/app/backtest.py` / `backtest_service.py` | `skip_earnings_days` |
| `backend/app/main.py` | Earnings route + scanner/detail enrichment |
| `backend/tests/test_earnings.py` | Unit tests |
| `backend/tests/test_earnings_api.py` | API / enrichment tests |

**Endpoints**

- `GET /api/tickers/{symbol}/earnings`
- Scanner / ticker detail fields: `next_earnings_date`, `days_until_earnings`, `earnings_risk` (+ `earnings_time_of_day` on detail)
- Backtest: `skip_earnings_days`, response `earnings_trades_skipped`, `earnings_data_unavailable`

### Frontend

| Path | Role |
| --- | --- |
| `frontend/src/api.ts` | Types + `getTickerEarnings` |
| `frontend/src/pages/ScannerPage.tsx` | Earnings column |
| `frontend/src/pages/TickerDetailPage.tsx` | Warning banner |
| `frontend/src/pages/BacktestPage.tsx` | Skip-near-earnings input + result note |
| `frontend/src/App.css` | Badge / banner styles |

## Env

```text
FINNHUB_API_KEY=your_finnhub_api_key
```

No Alembic migration (checklist rule seeded at startup / `GET /api/checklists`).

## Run

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
# set FINNHUB_API_KEY in .env
pytest
uvicorn app.main:app --reload --host 127.0.0.1 --port 9002

cd frontend
npm run dev
```
