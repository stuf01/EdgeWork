# Feature: Trade Journal

**Source prompt:** `Prompt-6.txt`  
**Status:** Implemented

## Summary

Turns saved plans into a journal with lifecycle (`planned` → `open` → `closed` / `skipped`), realized P&amp;L and R-multiples, expectancy / drawdown stats, setup-tag breakdowns, and a cumulative P&amp;L chart.

## Requirements (from prompt)

- New plan columns: status, paper flag, setup tag, actual entry/exit, shares traded, exit reason, opened/closed timestamps, lessons
- Pure `journal.py`: realized PnL, R-multiple, `compute_stats`, `stats_by_tag`
- `PATCH /api/plans/{id}` with close validation; `GET /api/journal/stats` with filters
- Journal page: stats cards, by-setup table, filters, sortable plan table, row actions
- Paper/real + setup tag on Planner and on-chart save
- Small-sample note when &lt; 30 closed trades

## What was built

### Backend

| Path | Role |
| --- | --- |
| `backend/app/journal.py` | PnL, R, stats, drawdown, by-tag |
| `backend/app/models.py` | Journal fields on `TradePlan` |
| `backend/app/crud.py` | Plan patch / close validation |
| `backend/app/schemas.py` | Patch + stats response models |
| `backend/alembic/versions/a1b2c3d4e5f6_add_trade_plan_journal_fields.py` | Migration (existing rows → `planned`) |

**Endpoints**

- `PATCH /api/plans/{id}`
- `GET /api/journal/stats?is_paper=&setup_tag=&from=&to=`

### Frontend

| Path | Role |
| --- | --- |
| `frontend/src/pages/JournalPage.tsx` | Stats, filters, table, open/close/edit modals |
| `frontend/src/components/CumPnlChart.tsx` | Cumulative P&amp;L line |
| `frontend/src/pages/PlannerPage.tsx` | Setup tag + paper/real on save |
| `frontend/src/pages/TickerDetailPage.tsx` | Same fields in on-chart save |
| `frontend/src/App.tsx` | `/journal` nav link |

### Tests

- Unit: PnL, R, empty / all-wins / all-losses, hand-calculated drawdown, by-tag
- API: transitions, close without required fields → 422, filtered stats
- Migration survival: legacy row keeps `status=planned`
