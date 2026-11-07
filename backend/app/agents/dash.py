"""DASH — Reviewer. Grades and suggests only; never edits settings/rules/code."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.schemas import DashReport, DashTradeGrade
from app.journal import compute_stats
from app.models import AgentEvent, Proposal, TradePlan

HUNDRED = Decimal("100")


def run_dash(db: Session, *, lookback_days: int = 7) -> DashReport:
    """Build a weekly-style review report from recent agent activity."""
    since = datetime.now(timezone.utc) - timedelta(days=lookback_days)

    proposals = list(
        db.scalars(
            select(Proposal).where(Proposal.created_at >= since).order_by(Proposal.id)
        )
    )
    events = list(
        db.scalars(
            select(AgentEvent).where(AgentEvent.created_at >= since).order_by(AgentEvent.id)
        )
    )

    grades: list[DashTradeGrade] = []
    closed_for_stats = []
    for proposal in proposals:
        if proposal.status != "executed" or proposal.journal_plan_id is None:
            continue
        plan = db.get(TradePlan, proposal.journal_plan_id)
        if plan is None or plan.status != "closed":
            continue
        grade = _grade_closed(proposal, plan)
        grades.append(grade)
        if plan.actual_entry is not None and plan.actual_exit is not None:
            closed_for_stats.append(plan)

    from app.journal import ClosedTrade

    closed_trades = []
    for plan in closed_for_stats:
        closed_trades.append(
            ClosedTrade(
                actual_entry=plan.actual_entry,
                actual_exit=plan.actual_exit,
                shares_traded=plan.shares_traded or 0,
                actual_risk=plan.actual_risk,
                setup_tag=plan.setup_tag,
                closed_at=plan.closed_at or plan.created_at,
            )
        )
    stats = compute_stats(closed_trades)

    veto_reasons: dict[str, int] = {}
    for proposal in proposals:
        if proposal.status != "vetoed" or not proposal.vesk_result:
            continue
        try:
            payload = json.loads(proposal.vesk_result)
            reasons = payload if isinstance(payload, list) else payload.get("reasons", [])
        except json.JSONDecodeError:
            reasons = [proposal.vesk_result]
        for reason in reasons:
            key = str(reason)
            veto_reasons[key] = veto_reasons.get(key, 0) + 1

    stage_timings = _stage_timings(events)
    slowest = None
    if stage_timings:
        slowest = max(stage_timings.items(), key=lambda item: item[1])[0]

    expired_unapproved = sum(
        1
        for proposal in proposals
        if proposal.status == "expired" and proposal.approved_at is None
    )

    calibration = _orin_calibration(grades)
    experiments = _suggest_experiments(
        stats.expectancy_r,
        veto_reasons,
        slowest,
        expired_unapproved,
        grades,
    )

    return DashReport(
        win_rate=stats.win_rate,
        expectancy_r=stats.expectancy_r,
        grades=grades,
        orin_calibration=calibration,
        veto_reasons=veto_reasons,
        stage_timings_ms=stage_timings,
        slowest_stage=slowest,
        expired_unapproved=expired_unapproved,
        suggested_experiments=experiments,
    )


def _grade_closed(proposal: Proposal, plan: TradePlan) -> DashTradeGrade:
    process = "A"
    if plan.setup_tag != "agent-loop":
        process = "C"
    if plan.is_paper is False:
        process = "F"
    if plan.actual_entry is not None and proposal.entry is not None:
        if abs(plan.actual_entry - proposal.entry) / proposal.entry > Decimal("0.01"):
            process = "D" if process == "A" else process

    r_mult = None
    if (
        plan.actual_entry is not None
        and plan.actual_exit is not None
        and plan.shares_traded
        and plan.actual_risk
    ):
        from app.journal import realized_pnl, r_multiple

        pnl = realized_pnl(plan.actual_entry, plan.actual_exit, plan.shares_traded)
        r_mult = r_multiple(pnl, plan.actual_risk)

    if r_mult is None:
        outcome = "C"
    elif r_mult >= Decimal("2"):
        outcome = "A"
    elif r_mult >= Decimal("1"):
        outcome = "B"
    elif r_mult >= 0:
        outcome = "C"
    elif r_mult >= Decimal("-1"):
        outcome = "D"
    else:
        outcome = "F"

    actual_move = None
    if plan.actual_entry and plan.actual_exit and plan.actual_entry != 0:
        actual_move = (
            (plan.actual_exit - plan.actual_entry) / plan.actual_entry * HUNDRED
        )

    return DashTradeGrade(
        proposal_id=proposal.id,
        symbol=proposal.symbol,
        process_grade=process,
        outcome_grade=outcome,
        r_multiple=r_mult,
        orin_expected_move_percent=proposal.orin_expected_move_percent,
        actual_move_percent=actual_move,
    )


def _stage_timings(events: list[AgentEvent]) -> dict[str, float]:
    totals: dict[str, list[int]] = {}
    for event in events:
        if event.duration_ms is None:
            continue
        if event.event_type not in ("stage_complete", "cycle_stage"):
            # Prefer duration on stage events; also accept agent stage markers.
            if not event.event_type.endswith("_done") and event.event_type != "run":
                continue
        bucket = event.agent
        totals.setdefault(bucket, []).append(event.duration_ms)
    # Also collect any duration_ms by agent regardless of type for cycle stages.
    for event in events:
        if event.duration_ms is None:
            continue
        if event.agent in ("NOVA", "ORIN", "VESK", "LUMA", "KIRA", "DASH"):
            totals.setdefault(event.agent, []).append(event.duration_ms)
    return {
        agent: (sum(values) / len(values))
        for agent, values in totals.items()
        if values
    }


def _orin_calibration(grades: list[DashTradeGrade]) -> list[dict[str, Any]]:
    buckets: dict[str, list[tuple[Decimal, Decimal]]] = {
        "0-39": [],
        "40-59": [],
        "60-79": [],
        "80-100": [],
    }
    # We only have expected/actual moves on grades; score buckets need proposal score.
    # Approximate by expected move magnitude when score unknown.
    for grade in grades:
        if grade.orin_expected_move_percent is None or grade.actual_move_percent is None:
            continue
        expected = abs(grade.orin_expected_move_percent)
        if expected < 1:
            key = "0-39"
        elif expected < 2:
            key = "40-59"
        elif expected < 4:
            key = "60-79"
        else:
            key = "80-100"
        buckets[key].append((grade.orin_expected_move_percent, grade.actual_move_percent))

    rows: list[dict[str, Any]] = []
    for key, pairs in buckets.items():
        if not pairs:
            rows.append(
                {
                    "bucket": key,
                    "count": 0,
                    "avg_predicted": None,
                    "avg_actual": None,
                }
            )
            continue
        avg_p = sum((p[0] for p in pairs), Decimal("0")) / Decimal(len(pairs))
        avg_a = sum((p[1] for p in pairs), Decimal("0")) / Decimal(len(pairs))
        rows.append(
            {
                "bucket": key,
                "count": len(pairs),
                "avg_predicted": format(avg_p, "f"),
                "avg_actual": format(avg_a, "f"),
            }
        )
    return rows


def _suggest_experiments(
    expectancy_r: Optional[Decimal],
    veto_reasons: dict[str, int],
    slowest: Optional[str],
    expired_unapproved: int,
    grades: list[DashTradeGrade],
) -> list[str]:
    suggestions: list[str] = []
    if expectancy_r is not None and expectancy_r <= 0:
        suggestions.append(
            "Expectancy is at or below zero — tighten checklist required rules "
            "or raise min ORIN score before enabling more size."
        )
    if veto_reasons:
        top = max(veto_reasons.items(), key=lambda item: item[1])[0]
        suggestions.append(
            f"Most common VESK veto is '{top}' — review whether that rule is "
            "too strict for your watchlist or reflecting real risk."
        )
    if slowest:
        suggestions.append(
            f"{slowest} is the slowest stage on average — profile data fetches "
            "or cache warm-up for that agent."
        )
    if expired_unapproved > 0:
        suggestions.append(
            f"{expired_unapproved} proposals expired without approval — "
            "shorten the cycle interval or extend proposal TTL during your session."
        )
    if not suggestions:
        suggestions.append(
            "Collect at least 30 closed agent-loop trades before changing risk percent."
        )
        suggestions.append(
            "Compare ORIN calibration buckets weekly and only raise size when "
            "high-score buckets stay predictive."
        )
    return suggestions[:3]
