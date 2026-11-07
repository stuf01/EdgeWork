# Feature: Gap-and-Breakout Backtester

**Source prompt:** `Prompt-8.txt`  
**Status:** Implemented

## Summary

Daily-bar long-side gap-and-breakout backtester with documented lookahead rules, same-bar stop-first assumption, costs, position sizing via planner math, persisted runs, equity curve, and two-run compare UI.

## Requirements (from prompt)

- Pure `backtest.py` over daily bars: gap / prior-day RVol filters, `break_prev_high` entry, stop rules, target in R, costs, max 5 trades/day
- Limits: 50 symbols, 3 years; per-symbol provider errors collected
- `BacktestRun` ORM (parameters/symbols/summary/trades as JSON)
- Endpoints: create / list / get / delete; optional `use_watchlist`
- Backtest page: form, assumptions banner, &lt;100 trades warning, past runs + compare

## What was built

### Backend

| Path | Role |
| --- | --- |
| `backend/app/backtest.py` | Pure engine (lookahead comment, stop-first same bar) |
| `backend/app/backtest_service.py` | Fetch bars, persist runs, symbol resolution |
| `backend/app/models.py` | `BacktestRun` |
| `backend/alembic/versions/c3d4e5f6a7b8_add_backtest_runs.py` | Migration |
| `backend/app/main.py` | Backtest routes |
| `backend/app/journal.py` | Reused `compute_stats` / drawdown for summary |

**Endpoints**

- `POST /api/backtests`
- `GET /api/backtests`
- `GET /api/backtests/{id}`
- `DELETE /api/backtests/{id}`

**Default parameters (examples):** min gap 2%, min RVol 2, min price 5, min avg volume 500k, stop `fixed_percent` 2%, target 2R, cost $0.02/share, risk 1%, starting account $10,000.

### Frontend

| Path | Role |
| --- | --- |
| `frontend/src/pages/BacktestPage.tsx` | Form, results, past runs, compare |
| `frontend/src/components/EquityCurveChart.tsx` | Equity curve |
| `frontend/src/App.tsx` | `/backtest` nav |
| `frontend/src/api.ts` | Backtest client types |

### Tests

- Hand-built series: win, loss, close exit, same-bar stop+target → loss, gap-open entry, skip short history, costs subtracted
- No-lookahead proof (today’s volume change does not alter qualification)
- API: run/list/get/delete, validation, bad symbol → `errors`
