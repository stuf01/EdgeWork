# Feature: Six-Agent Paper-Trading Pipeline

**Source prompt:** `Prompt-10.txt`  
**Status:** Implemented

## Summary

Multi-agent paper-trading loop that reuses scanner, checklist, planner, levels, news, earnings, journal, and backtest. Humans approve before any order; VESK vetoes are final; KIRA is paper-only against Alpaca paper API.

## Global rules (enforced in code + README)

1. **One job per agent** — modules under `backend/app/agents/`, one public function each, typed Pydantic I/O
2. **Risk has the final no** — VESK veto cannot be overridden by UI, settings, or API (tested)
3. **Human approves before execute** — KIRA only acts on `approved` proposals
4. **Paper only** — refuse unless `ALPACA_PAPER_URL` is exactly `https://paper-api.alpaca.markets`
5. **Full event log** — signals, scores, vetoes, decisions, approvals, orders, reviews

## What was built

### Backend

| Path | Role |
| --- | --- |
| `backend/app/agents/nova.py` | Watchlist + checklist candidates + level derivation |
| `backend/app/agents/orin.py` | Statistical/rule score + expected move |
| `backend/app/agents/vesk.py` | Sizing + multi-reason veto (final) |
| `backend/app/agents/luma.py` | PROPOSE / WATCH / SKIP / VETO (never overrides veto) |
| `backend/app/agents/kira.py` | Paper bracket orders after human approval |
| `backend/app/agents/dash.py` | Process/outcome grades + weekly-style report |
| `backend/app/agents/cycle.py` | Orchestration + event timings |
| `backend/app/agents/paper_client.py` | Alpaca paper + fake client |
| `backend/app/agents/api.py` | REST endpoints |
| `backend/app/agents/scheduler.py` | Optional APScheduler (off by default) |
| `backend/alembic/versions/d4e5f6a7b8c9_add_agent_tables.py` | Migration |
| `backend/tests/test_agents.py` | Unit + API coverage |

### Frontend

| Path | Role |
| --- | --- |
| `frontend/src/pages/AgentsPage.tsx` | Control / Proposals / Activity / Review tabs |
| `frontend/src/api.ts` | Typed agent client |
| `frontend/src/App.tsx` | `/agents` nav route |

### Endpoints

- `GET/PUT /api/agents/settings`
- `POST /api/agents/kill-switch`
- `POST /api/agents/run-cycle`
- `GET /api/agents/proposals?status=`
- `POST /api/agents/proposals/{id}/approve` / `reject` (no veto override)
- `GET /api/agents/events`
- `POST /api/agents/review/run`, `GET /api/agents/review/latest`

## Env

```text
ALPACA_PAPER_URL=https://paper-api.alpaca.markets
ALPACA_API_KEY=...
ALPACA_API_SECRET=...
```

## Run

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
alembic upgrade head
pytest
uvicorn app.main:app --reload --host 127.0.0.1 --port 9002

cd frontend
npm run dev
```

Open `http://localhost:9001/agents`.
