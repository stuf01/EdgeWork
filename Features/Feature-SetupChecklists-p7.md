# Feature: Setup Checklists

**Source prompt:** `Prompt-7.txt`  
**Status:** Implemented

## Summary

Configurable rule checklists that score a trade idea from live market context. Default seeded checklist is **Breakout basics**. Scores can be stored on plans and compared in journal stats (met ≥70 vs below).

## Requirements (from prompt)

- Models: `Checklist`, `ChecklistRule`; plan fields `checklist_id`, `checklist_score`
- Seed “Breakout basics” rules (gap, RVol, news, VWAP, prior high, R:R, SMA20)
- Pure `checklist.py`: registry, evaluate, score, verdict (“Meets your rules” if score ≥70 and no required failures)
- CRUD + `POST /api/checklists/{id}/evaluate` (backend builds context; unknown ≠ hard fail)
- On-chart evaluate UI; Checklists settings page; journal score comparison card

## What was built

### Backend

| Path | Role |
| --- | --- |
| `backend/app/checklist.py` | Registry, evaluate, score, seed rules |
| `backend/app/checklist_context.py` | Build context from provider + planner math |
| `backend/app/models.py` | Checklist / rules / plan FKs |
| `backend/app/crud.py` | Checklist CRUD + validation |
| `backend/alembic/versions/b2c3d4e5f6a7_add_checklists.py` | Migration |
| `backend/app/main.py` | Checklist routes; plan create stores score; journal stats breakdown |

**Rule types registered (examples):** `gap_percent`, `relative_volume`, `avg_daily_volume`, `last_price`, `has_recent_news`, `price_above_vwap`, `price_above_prev_day_high`, `price_above_prev_day_low`, `entry_above_sma_20`, `entry_above_sma_50`, `risk_reward`, `spread_percent`, `stop_distance_percent`.

**Endpoints**

- `GET/POST /api/checklists`
- `PUT/DELETE /api/checklists/{id}`
- `POST /api/checklists/{id}/evaluate`

### Frontend

| Path | Role |
| --- | --- |
| `frontend/src/pages/ChecklistsPage.tsx` | Create/edit/delete rules, reorder |
| `frontend/src/pages/TickerDetailPage.tsx` | Checklist dropdown + evaluate on line changes |
| `frontend/src/pages/JournalPage.tsx` | Met-rules vs below-70 card |
| `frontend/src/lib/checklistPanel.ts` | Panel layout helpers |
| `frontend/src/App.tsx` | `/checklists` route |

Negative verdict does not block saving a plan (amber note only).

### Tests

- Evaluate/score: all pass, required fail, unknown, boundaries, verdict
- API: evaluate, missing data → unknown, invalid rule_type, score saved on plan
