# Feature: Trade Planner & Project Scaffold

**Source prompt:** `Prompt-1.txt`  
**Status:** Implemented

## Summary

Monorepo scaffolding for EdgeWork plus the first product feature: a long-only trade planner that sizes positions from account size, risk percent, entry, stop, and target. Money math uses `Decimal` end to end (never floats).

## Requirements (from prompt)

- Backend: Python 3.11+, FastAPI, uvicorn, Pydantic v2, SQLAlchemy 2.0 (`Mapped[]`), Alembic, pytest, SQLite
- Frontend: React + Vite + TypeScript (strict), plain CSS, no UI framework
- Pure `calculate_plan()` with floor shares, R:R, position cost, `exceeds_account`
- `TradePlan` ORM with `DecimalString` TEXT columns for money
- Endpoints: calculate, create, list, delete
- Planner UI with calculate/save and saved-plans table
- Vite proxy `/api` → `http://localhost:9002`; CORS for `http://localhost:9001`

## What was built

### Backend

| Path | Role |
| --- | --- |
| `backend/app/main.py` | FastAPI app, CORS, plan routes |
| `backend/app/planner.py` | Pure sizing math |
| `backend/app/database.py` | Engine, `get_db`, SQLite FK pragma |
| `backend/app/models.py` | `TradePlan`, `DecimalString` |
| `backend/app/schemas.py` | Request/response models (money as strings) |
| `backend/app/crud.py` | Create / list / delete plans |
| `backend/alembic/versions/9f9bc63c3827_create_trade_plans_table.py` | Initial migration |
| `backend/data/trading.db` | SQLite DB (gitignored) |

**Endpoints**

- `POST /api/plans/calculate`
- `POST /api/plans`
- `GET /api/plans`
- `DELETE /api/plans/{id}`

### Frontend

| Path | Role |
| --- | --- |
| `frontend/src/pages/PlannerPage.tsx` | Form, results card, saved plans |
| `frontend/src/api.ts` | Typed client (grew with later features) |
| `frontend/vite.config.ts` | Dev server `:9001`, `/api` proxy to `:9002` |
| `README.md` | Root setup / run docs |

### Tests

- Planner unit cases (including 10k / 1% / 40 / 39.50 / 41.50 → 200 shares, R:R 3)
- API TestClient coverage for calculate / save / list / delete
- Decimal round-trip through SQLite

## Run

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
alembic upgrade head
pytest
uvicorn app.main:app --reload --host 127.0.0.1 --port 9002

cd frontend
npm install
npm run dev
```
