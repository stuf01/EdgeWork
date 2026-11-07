"""Event-log helpers for the agent pipeline."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models import AgentEvent


def log_event(
    db: Session,
    *,
    cycle_id: str,
    agent: str,
    event_type: str,
    payload: Optional[dict[str, Any]] = None,
    symbol: Optional[str] = None,
    proposal_id: Optional[int] = None,
    duration_ms: Optional[int] = None,
    commit: bool = True,
) -> AgentEvent:
    """Persist one agent event. Never logs secrets."""
    event = AgentEvent(
        created_at=datetime.now(timezone.utc),
        cycle_id=cycle_id,
        agent=agent,
        event_type=event_type,
        symbol=symbol,
        proposal_id=proposal_id,
        duration_ms=duration_ms,
        payload=json.dumps(payload or {}, default=str),
    )
    db.add(event)
    if commit:
        db.commit()
        db.refresh(event)
    else:
        db.flush()
    return event
