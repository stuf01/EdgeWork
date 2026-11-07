# EdgeWork — day-trading research

Monorepo for a day-trading research tool: **trade planner**, **watchlist**, **scanner**, **ticker charts** (candles, VWAP, key levels), and **ticker news** via Alpaca.

## Structure

- `backend/` — Python 3.11+, FastAPI, SQLAlchemy 2.0, Alembic, pytest (SQLite)
- `frontend/` — React + Vite + TypeScript (strict), react-router, plain CSS

Ports: frontend `http://localhost:9001`, API `http://localhost:9002`.

## Backend setup

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
# Edit .env and set ALPACA_API_KEY / ALPACA_API_SECRET
alembic upgrade head
```

If you need a new virtualenv:

```powershell
cd backend
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
alembic upgrade head
```

### Environment (`.env`)

Copy `backend/.env.example` → `backend/.env` (gitignored):

```text
ALPACA_API_KEY=your_alpaca_api_key
ALPACA_API_SECRET=your_alpaca_api_secret
ALPACA_DATA_URL=https://data.alpaca.markets
```

### Run migrations

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
alembic upgrade head
```

### Run API

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --host 127.0.0.1 --port 9002
```

### Run tests & lint

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
pytest
flake8 app tests
```

Database file: `backend/data/trading.db`. Schema changes go through Alembic only; the app does **not** call `create_all`.

## Frontend setup

```powershell
cd frontend
npm install
npm run dev
```

Vite proxies `/api` to `http://127.0.0.1:9002`.

## Quick start (both servers)

Terminal 1:

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
alembic upgrade head
uvicorn app.main:app --reload --host 127.0.0.1 --port 9002
```

Terminal 2:

```powershell
cd frontend
npm install
npm run dev
```

Open `http://localhost:9001` (Planner), `http://localhost:9001/scanner`, or a ticker page such as `http://localhost:9001/ticker/AAPL`.
