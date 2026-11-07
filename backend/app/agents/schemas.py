"""Typed Pydantic I/O for each agent (one job per agent)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_serializer


def _dec(value: Decimal) -> str:
    return format(value, "f")


class NovaCandidate(BaseModel):
    symbol: str
    entry: Decimal
    stop: Decimal
    target: Decimal
    checklist_score: int
    gap_percent: Optional[Decimal] = None
    relative_volume: Optional[Decimal] = None
    last_price: Optional[Decimal] = None
    has_recent_news: Optional[bool] = None
    days_until_earnings: Optional[int] = None
    context: dict[str, Any] = Field(default_factory=dict)

    @field_serializer("entry", "stop", "target", "gap_percent", "relative_volume", "last_price")
    def ser_dec(self, value: Optional[Decimal]) -> Optional[str]:
        if value is None:
            return None
        return _dec(value)


class NovaInput(BaseModel):
    cycle_id: str
    checklist_id: Optional[int] = None
    min_checklist_score: int = 70


class NovaOutput(BaseModel):
    candidates: list[NovaCandidate]
    skipped: list[dict[str, Any]] = Field(default_factory=list)


class OrinScore(BaseModel):
    symbol: str
    score: int
    expected_move_percent: Decimal
    sample_count: int
    low_confidence: bool
    factors: dict[str, Any] = Field(default_factory=dict)

    @field_serializer("expected_move_percent")
    def ser_move(self, value: Decimal) -> str:
        return _dec(value)


class OrinInput(BaseModel):
    cycle_id: str
    candidates: list[NovaCandidate]


class OrinOutput(BaseModel):
    scores: list[OrinScore]


class VeskCheckInput(BaseModel):
    cycle_id: str
    symbol: str
    entry: Decimal
    stop: Decimal
    target: Decimal
    account_size: Decimal
    risk_percent: Decimal
    buying_power: Decimal
    open_positions: int
    max_open_positions: int
    trades_today: int
    max_trades_per_day: int
    daily_pnl: Decimal
    daily_loss_limit_percent: Decimal
    has_open_or_pending: bool
    days_until_earnings: Optional[int] = None
    market_open: bool
    within_open_buffer: bool
    last_price: Optional[Decimal] = None


class VeskResult(BaseModel):
    symbol: str
    approved: bool
    shares: int = 0
    max_loss: Optional[Decimal] = None
    reasons: list[str] = Field(default_factory=list)

    @field_serializer("max_loss")
    def ser_loss(self, value: Optional[Decimal]) -> Optional[str]:
        if value is None:
            return None
        return _dec(value)


class VeskInput(BaseModel):
    cycle_id: str
    checks: list[VeskCheckInput]


class VeskOutput(BaseModel):
    results: list[VeskResult]


LumaDecisionKind = Literal["PROPOSE", "WATCH", "SKIP", "VETO"]


class LumaDecision(BaseModel):
    symbol: str
    decision: LumaDecisionKind
    reasoning: str
    entry: Decimal
    stop: Decimal
    target: Decimal
    shares: Optional[int] = None
    max_loss: Optional[Decimal] = None
    orin_score: Optional[int] = None
    orin_expected_move_percent: Optional[Decimal] = None
    checklist_score: Optional[int] = None
    vesk_reasons: list[str] = Field(default_factory=list)

    @field_serializer(
        "entry",
        "stop",
        "target",
        "max_loss",
        "orin_expected_move_percent",
    )
    def ser_dec(self, value: Optional[Decimal]) -> Optional[str]:
        if value is None:
            return None
        return _dec(value)


class LumaInput(BaseModel):
    cycle_id: str
    candidates: list[NovaCandidate]
    orin_scores: list[OrinScore]
    vesk_results: list[VeskResult]
    min_orin_score: int = 60
    min_checklist_score: int = 70


class LumaOutput(BaseModel):
    decisions: list[LumaDecision]


class KiraInput(BaseModel):
    proposal_id: int
    symbol: str
    status: str
    entry: Decimal
    stop: Decimal
    target: Decimal
    shares: int
    expires_at: Optional[datetime] = None
    last_price: Optional[Decimal] = None
    paper_url: str
    client_order_id: str


class KiraOutput(BaseModel):
    executed: bool
    status: str
    order_id: Optional[str] = None
    reason: Optional[str] = None
    journal_plan_id: Optional[int] = None


class DashTradeGrade(BaseModel):
    proposal_id: int
    symbol: str
    process_grade: str
    outcome_grade: str
    r_multiple: Optional[Decimal] = None
    orin_expected_move_percent: Optional[Decimal] = None
    actual_move_percent: Optional[Decimal] = None

    model_config = ConfigDict(arbitrary_types_allowed=True)

    @field_serializer("r_multiple", "orin_expected_move_percent", "actual_move_percent")
    def ser_dec(self, value: Optional[Decimal]) -> Optional[str]:
        if value is None:
            return None
        return _dec(value)


class DashReport(BaseModel):
    win_rate: Optional[Decimal] = None
    expectancy_r: Optional[Decimal] = None
    grades: list[DashTradeGrade] = Field(default_factory=list)
    orin_calibration: list[dict[str, Any]] = Field(default_factory=list)
    veto_reasons: dict[str, int] = Field(default_factory=dict)
    stage_timings_ms: dict[str, float] = Field(default_factory=dict)
    slowest_stage: Optional[str] = None
    expired_unapproved: int = 0
    suggested_experiments: list[str] = Field(default_factory=list)

    @field_serializer("win_rate", "expectancy_r")
    def ser_dec(self, value: Optional[Decimal]) -> Optional[str]:
        if value is None:
            return None
        return _dec(value)


class CycleSummary(BaseModel):
    cycle_id: str
    skipped: bool = False
    skip_reason: Optional[str] = None
    nova_candidates: int = 0
    orin_scores: int = 0
    vesk_approved: int = 0
    vesk_vetoed: int = 0
    proposed: int = 0
    watched: int = 0
    skipped_decisions: int = 0
    stage_timings_ms: dict[str, int] = Field(default_factory=dict)
