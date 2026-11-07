# Backend — Trade Planner / Scanner API

FastAPI service for trade plans, watchlist, and watchlist scanner (Alpaca IEX).

## Setup

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
# Set ALPACA_API_KEY and ALPACA_API_SECRET
alembic upgrade head
```

## Run

```powershell
uvicorn app.main:app --reload --host 127.0.0.1 --port 9002
```

CORS allows `http://localhost:9001`.

## Tests & lint

```powershell
pytest
flake8 app tests
```

## Endpoints

| Method | Path | Notes |
| --- | --- | --- |
| POST | `/api/plans/calculate` | calculates only |
| POST | `/api/plans` | calculate and save |
| GET | `/api/plans` | newest first |
| DELETE | `/api/plans/{id}` | 404 if missing |
| GET | `/api/watchlist` | list symbols |
| POST | `/api/watchlist` | add symbol (409 duplicate) |
| DELETE | `/api/watchlist/{symbol}` | remove symbol |
| GET | `/api/scanner` | scan watchlist with filters (+ optional news flags) |
| GET | `/api/tickers/{symbol}/detail` | chart bars, VWAP, levels |
| GET | `/api/tickers/{symbol}/news` | recent headlines + 24h flags |

## Database

- SQLite: `data/trading.db`
- Run `alembic upgrade head` after install/pull
- Money columns use `DecimalString` (TEXT) so values stay `Decimal`
