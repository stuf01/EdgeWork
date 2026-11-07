"""Check journal migration leaves existing plan rows as status=planned."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text


ROOT = Path(__file__).resolve().parents[1]
ALEMBIC_INI = ROOT / "alembic.ini"


@pytest.fixture()
def alembic_cfg(tmp_path, monkeypatch: pytest.MonkeyPatch) -> Config:
    db_path = tmp_path / "journal_mig.db"
    url = f"sqlite:///{db_path.as_posix()}"
    monkeypatch.setattr("app.database.DATABASE_URL", url)
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def test_existing_plan_survives_journal_migration(alembic_cfg: Config) -> None:
    command.upgrade(alembic_cfg, "2d375de1169c")

    url = alembic_cfg.get_main_option("sqlalchemy.url")
    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO trade_plans (
                    created_at, symbol, account_size, risk_percent,
                    entry, stop, target, shares, actual_risk, risk_reward, notes
                ) VALUES (
                    :created_at, :symbol, :account_size, :risk_percent,
                    :entry, :stop, :target, :shares, :actual_risk, :risk_reward, :notes
                )
                """
            ),
            {
                "created_at": datetime.now(timezone.utc).isoformat(),
                "symbol": "LEGACY",
                "account_size": "10000",
                "risk_percent": "1",
                "entry": "40",
                "stop": "39.5",
                "target": "41.5",
                "shares": 200,
                "actual_risk": "100",
                "risk_reward": "3",
                "notes": "pre-journal",
            },
        )

    command.upgrade(alembic_cfg, "head")

    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT symbol, status, is_paper, setup_tag, notes "
                "FROM trade_plans WHERE symbol = 'LEGACY'"
            )
        ).one()
    engine.dispose()

    assert row.symbol == "LEGACY"
    assert row.status == "planned"
    assert row.is_paper in (1, True)
    assert row.setup_tag is None
    assert row.notes == "pre-journal"
