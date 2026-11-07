"""LUMA — Decider. Never turns a VESK veto into a proposal."""

from __future__ import annotations

from app.agents.schemas import (
    LumaDecision,
    LumaInput,
    LumaOutput,
    NovaCandidate,
    OrinScore,
    VeskResult,
)


def run_luma(body: LumaInput) -> LumaOutput:
    """Route each candidate to PROPOSE, WATCH, SKIP, or VETO."""
    orin_map = {item.symbol: item for item in body.orin_scores}
    vesk_map = {item.symbol: item for item in body.vesk_results}
    decisions: list[LumaDecision] = []
    for candidate in body.candidates:
        orin = orin_map.get(candidate.symbol)
        vesk = vesk_map.get(candidate.symbol)
        decisions.append(
            _decide(
                candidate,
                orin,
                vesk,
                min_orin_score=body.min_orin_score,
                min_checklist_score=body.min_checklist_score,
            )
        )
    return LumaOutput(decisions=decisions)


def _decide(
    candidate: NovaCandidate,
    orin: OrinScore | None,
    vesk: VeskResult | None,
    *,
    min_orin_score: int,
    min_checklist_score: int,
) -> LumaDecision:
    # Hard rule: VESK veto is final — LUMA cannot propose.
    if vesk is not None and not vesk.approved:
        reasons = ", ".join(vesk.reasons) or "unspecified"
        return LumaDecision(
            symbol=candidate.symbol,
            decision="VETO",
            reasoning=f"VESK vetoed this setup ({reasons}). Vetoes are final.",
            entry=candidate.entry,
            stop=candidate.stop,
            target=candidate.target,
            shares=0,
            max_loss=vesk.max_loss,
            orin_score=orin.score if orin else None,
            orin_expected_move_percent=(
                orin.expected_move_percent if orin else None
            ),
            checklist_score=candidate.checklist_score,
            vesk_reasons=list(vesk.reasons),
        )

    if candidate.checklist_score < min_checklist_score:
        return _skip(
            candidate,
            orin,
            vesk,
            f"Checklist score {candidate.checklist_score} is below "
            f"minimum {min_checklist_score}.",
        )

    if orin is None:
        return _skip(candidate, orin, vesk, "ORIN did not return a score.")

    if orin.score < min_orin_score:
        return LumaDecision(
            symbol=candidate.symbol,
            decision="WATCH",
            reasoning=(
                f"ORIN score {orin.score} is below minimum {min_orin_score}; "
                f"expected move {orin.expected_move_percent}% with "
                f"{orin.sample_count} samples"
                f"{' (low confidence)' if orin.low_confidence else ''}."
            ),
            entry=candidate.entry,
            stop=candidate.stop,
            target=candidate.target,
            shares=vesk.shares if vesk else None,
            max_loss=vesk.max_loss if vesk else None,
            orin_score=orin.score,
            orin_expected_move_percent=orin.expected_move_percent,
            checklist_score=candidate.checklist_score,
            vesk_reasons=[],
        )

    shares = vesk.shares if vesk else 0
    reasoning = (
        f"PROPOSE {candidate.symbol}: checklist {candidate.checklist_score}, "
        f"ORIN {orin.score} (expected {orin.expected_move_percent}%), "
        f"VESK approved {shares} shares."
    )
    if orin.low_confidence:
        reasoning += " ORIN flagged low confidence due to few historical samples."
    return LumaDecision(
        symbol=candidate.symbol,
        decision="PROPOSE",
        reasoning=reasoning,
        entry=candidate.entry,
        stop=candidate.stop,
        target=candidate.target,
        shares=shares,
        max_loss=vesk.max_loss if vesk else None,
        orin_score=orin.score,
        orin_expected_move_percent=orin.expected_move_percent,
        checklist_score=candidate.checklist_score,
        vesk_reasons=[],
    )


def _skip(
    candidate: NovaCandidate,
    orin: OrinScore | None,
    vesk: VeskResult | None,
    reason: str,
) -> LumaDecision:
    return LumaDecision(
        symbol=candidate.symbol,
        decision="SKIP",
        reasoning=reason,
        entry=candidate.entry,
        stop=candidate.stop,
        target=candidate.target,
        shares=vesk.shares if vesk else None,
        max_loss=vesk.max_loss if vesk else None,
        orin_score=orin.score if orin else None,
        orin_expected_move_percent=(
            orin.expected_move_percent if orin else None
        ),
        checklist_score=candidate.checklist_score,
        vesk_reasons=list(vesk.reasons) if vesk else [],
    )
