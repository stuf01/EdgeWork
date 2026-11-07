"""Human-readable activity-log summaries for agent stages."""

from __future__ import annotations

from typing import Any


def system_skipped(reason: str) -> dict[str, Any]:
    labels = {
        "kill_switch": "Kill switch is on — cycle not started",
        "disabled": "Agents are disabled — cycle not started",
        "market_closed": "Market is closed — cycle not started",
    }
    summary = labels.get(reason, f"Cycle skipped ({reason})")
    return {
        "reason": reason,
        "summary": summary,
        "details": [summary],
    }


def system_start(*, force: bool) -> dict[str, Any]:
    mode = "manual/forced" if force else "scheduled"
    summary = f"Cycle started ({mode})"
    return {
        "force": force,
        "summary": summary,
        "details": [
            summary,
            "Pipeline order: NOVA → ORIN → VESK → LUMA",
            "KIRA runs later only after human approval",
        ],
    }


def nova_stage(candidates: list[dict[str, Any]], skipped: list[dict[str, Any]]) -> dict[str, Any]:
    details: list[str] = [
        f"Scanned watchlist; kept {len(candidates)} candidate(s), "
        f"skipped {len(skipped)}",
    ]
    for row in candidates:
        details.append(
            f"{row.get('symbol')}: PASS checklist {row.get('checklist_score')} — "
            f"entry {row.get('entry')} / stop {row.get('stop')} / "
            f"target {row.get('target')} "
            f"(gap {row.get('gap_percent')}, rvol {row.get('relative_volume')})"
        )
    for row in skipped[:40]:
        symbol = row.get("symbol") or "—"
        reason = row.get("reason") or "skipped"
        extra = ""
        if row.get("required_failed"):
            extra = f" [{', '.join(row['required_failed'])}]"
        elif row.get("score") is not None:
            extra = f" (score {row.get('score')})"
        details.append(f"{symbol}: SKIP — {reason}{extra}")
    summary = (
        f"NOVA found {len(candidates)} setup(s); skipped {len(skipped)}"
        if candidates or skipped
        else "NOVA found no watchlist symbols to scan"
    )
    return {
        "candidates": candidates,
        "skipped": skipped,
        "summary": summary,
        "details": details,
    }


def orin_stage(scores: list[dict[str, Any]]) -> dict[str, Any]:
    details: list[str] = [f"Scored {len(scores)} candidate(s)"]
    for row in scores:
        conf = "low confidence" if row.get("low_confidence") else "ok samples"
        details.append(
            f"{row.get('symbol')}: score {row.get('score')}/100, "
            f"expected move {row.get('expected_move_percent')}%, "
            f"samples {row.get('sample_count')} ({conf})"
        )
    summary = (
        f"ORIN scored {len(scores)} symbol(s)"
        if scores
        else "ORIN had no candidates to score"
    )
    return {"scores": scores, "summary": summary, "details": details}


def vesk_stage(
    results: list[dict[str, Any]],
    *,
    account_size: str,
    buying_power: str,
    open_positions: int,
    trades_today: int,
) -> dict[str, Any]:
    approved = [r for r in results if r.get("approved")]
    vetoed = [r for r in results if not r.get("approved")]
    details: list[str] = [
        f"Account equity ~{account_size}, buying power ~{buying_power}",
        f"Open positions {open_positions}, agent trades today {trades_today}",
        f"Approved {len(approved)}, vetoed {len(vetoed)}",
    ]
    for row in approved:
        details.append(
            f"{row.get('symbol')}: APPROVED — {row.get('shares')} shares, "
            f"max loss {row.get('max_loss')}"
        )
    for row in vetoed:
        reasons = ", ".join(row.get("reasons") or []) or "unspecified"
        details.append(f"{row.get('symbol')}: VETO — {reasons}")
    summary = (
        f"VESK approved {len(approved)}, vetoed {len(vetoed)}"
        if results
        else "VESK had no candidates to check"
    )
    return {
        "results": results,
        "account_size": account_size,
        "buying_power": buying_power,
        "open_positions": open_positions,
        "trades_today": trades_today,
        "summary": summary,
        "details": details,
    }


def luma_stage(decisions: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {"PROPOSE": 0, "WATCH": 0, "SKIP": 0, "VETO": 0}
    details: list[str] = []
    for row in decisions:
        kind = str(row.get("decision") or "?")
        counts[kind] = counts.get(kind, 0) + 1
        details.append(
            f"{row.get('symbol')}: {kind} — {row.get('reasoning')}"
        )
    summary = (
        "LUMA "
        f"proposed {counts.get('PROPOSE', 0)}, "
        f"watch {counts.get('WATCH', 0)}, "
        f"skip {counts.get('SKIP', 0)}, "
        f"veto {counts.get('VETO', 0)}"
        if decisions
        else "LUMA made no decisions"
    )
    return {"decisions": decisions, "summary": summary, "details": details}


def luma_decision(decision: dict[str, Any]) -> dict[str, Any]:
    kind = decision.get("decision")
    symbol = decision.get("symbol")
    summary = f"LUMA {kind} on {symbol}"
    details = [
        summary,
        str(decision.get("reasoning") or ""),
        (
            f"Levels entry {decision.get('entry')} / stop {decision.get('stop')} "
            f"/ target {decision.get('target')}"
        ),
    ]
    if decision.get("shares") is not None:
        details.append(f"Shares {decision.get('shares')}, max loss {decision.get('max_loss')}")
    if decision.get("vesk_reasons"):
        details.append("VESK reasons: " + ", ".join(decision["vesk_reasons"]))
    payload = dict(decision)
    payload["summary"] = summary
    payload["details"] = [d for d in details if d]
    return payload


def system_complete(timings: dict[str, int], *, proposed: int, vetoed: int) -> dict[str, Any]:
    details = [f"{agent}: {ms} ms" for agent, ms in timings.items()]
    details.append(f"Pending proposals created: {proposed}")
    details.append(f"Vetoed proposals recorded: {vetoed}")
    summary = (
        f"Cycle finished in {sum(timings.values())} ms — "
        f"{proposed} proposed, {vetoed} vetoed"
    )
    return {
        "timings_ms": timings,
        "proposed": proposed,
        "vetoed": vetoed,
        "summary": summary,
        "details": details,
    }


def human_approval(action: str, symbol: str) -> dict[str, Any]:
    summary = f"Human {action}d {symbol}"
    return {"action": action, "summary": summary, "details": [summary]}


def kira_execution(result: dict[str, Any], symbol: str) -> dict[str, Any]:
    if result.get("executed"):
        summary = (
            f"KIRA executed paper bracket for {symbol} "
            f"(order {result.get('order_id')})"
        )
    else:
        summary = (
            f"KIRA did not trade {symbol}: "
            f"{result.get('reason') or result.get('status')}"
        )
    details = [
        summary,
        f"Status: {result.get('status')}",
        f"Journal plan id: {result.get('journal_plan_id')}",
    ]
    payload = dict(result)
    payload["summary"] = summary
    payload["details"] = details
    return payload
