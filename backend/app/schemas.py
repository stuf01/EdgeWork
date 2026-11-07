"""Pydantic v2 request and response schemas."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator

PlanStatus = Literal["planned", "open", "closed", "skipped"]
ExitReason = Literal["target_hit", "stop_hit", "manual_exit", "other"]


def _decimal_to_str(value: Decimal) -> str:
    return format(value, "f")


def _optional_decimal_to_str(value: Optional[Decimal]) -> Optional[str]:
    if value is None:
        return None
    return _decimal_to_str(value)


class CalculateRequest(BaseModel):
    """Body for calculate-only and shared price/risk fields."""

    account_size: Decimal = Field(..., gt=0)
    risk_percent: Decimal = Field(..., gt=0, le=100)
    entry: Decimal = Field(..., gt=0)
    stop: Decimal = Field(..., gt=0)
    target: Decimal = Field(..., gt=0)

    @field_validator("account_size", "risk_percent", "entry", "stop", "target", mode="before")
    @classmethod
    def _coerce_decimal(cls, value):
        if value is None:
            return value
        return Decimal(str(value))


class CreatePlanRequest(CalculateRequest):
    """Body for calculate-and-save."""

    symbol: str = Field(..., min_length=1, max_length=32)
    notes: Optional[str] = Field(default=None, max_length=1000)
    setup_tag: Optional[str] = Field(default=None, max_length=64)
    is_paper: bool = True
    checklist_id: Optional[int] = None

    @field_validator("symbol")
    @classmethod
    def _uppercase_symbol(cls, value: str) -> str:
        cleaned = value.strip().upper()
        if not cleaned:
            raise ValueError("symbol must not be empty")
        return cleaned

    @field_validator("setup_tag")
    @classmethod
    def _clean_setup_tag(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class UpdatePlanRequest(BaseModel):
    """Partial update for journal lifecycle fields."""

    status: Optional[PlanStatus] = None
    notes: Optional[str] = Field(default=None, max_length=1000)
    setup_tag: Optional[str] = Field(default=None, max_length=64)
    is_paper: Optional[bool] = None
    actual_entry: Optional[Decimal] = Field(default=None, gt=0)
    actual_exit: Optional[Decimal] = Field(default=None, gt=0)
    shares_traded: Optional[int] = Field(default=None, gt=0)
    exit_reason: Optional[ExitReason] = None
    lessons: Optional[str] = None

    @field_validator("actual_entry", "actual_exit", mode="before")
    @classmethod
    def _coerce_optional_decimal(cls, value):
        if value is None or value == "":
            return None
        return Decimal(str(value))

    @field_validator("setup_tag")
    @classmethod
    def _clean_setup_tag(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class CalculateResponse(BaseModel):
    """Result of a plan calculation (not persisted)."""

    max_risk_dollars: Decimal
    risk_per_share: Decimal
    shares: int
    actual_risk_dollars: Decimal
    reward_per_share: Decimal
    potential_profit: Decimal
    risk_reward_ratio: Decimal
    position_cost: Decimal
    exceeds_account: bool

    @field_serializer(
        "max_risk_dollars",
        "risk_per_share",
        "actual_risk_dollars",
        "reward_per_share",
        "potential_profit",
        "risk_reward_ratio",
        "position_cost",
    )
    def serialize_money(self, value: Decimal) -> str:
        return _decimal_to_str(value)


class TradePlanResponse(BaseModel):
    """A persisted trade plan / journal entry."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    symbol: str
    account_size: Decimal
    risk_percent: Decimal
    entry: Decimal
    stop: Decimal
    target: Decimal
    shares: int
    actual_risk: Decimal
    risk_reward: Decimal
    notes: Optional[str] = None
    status: PlanStatus = "planned"
    is_paper: bool = True
    setup_tag: Optional[str] = None
    actual_entry: Optional[Decimal] = None
    actual_exit: Optional[Decimal] = None
    shares_traded: Optional[int] = None
    exit_reason: Optional[ExitReason] = None
    opened_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    lessons: Optional[str] = None
    realized_pnl: Optional[Decimal] = None
    r_multiple: Optional[Decimal] = None
    checklist_id: Optional[int] = None
    checklist_score: Optional[int] = None

    @field_serializer(
        "account_size",
        "risk_percent",
        "entry",
        "stop",
        "target",
        "actual_risk",
        "risk_reward",
    )
    def serialize_money(self, value: Decimal) -> str:
        return _decimal_to_str(value)

    @field_serializer("actual_entry", "actual_exit", "realized_pnl", "r_multiple")
    def serialize_optional_money(self, value: Optional[Decimal]) -> Optional[str]:
        return _optional_decimal_to_str(value)


class JournalStatsBlock(BaseModel):
    """One stats aggregate (overall or per tag)."""

    total_trades: int
    wins: int
    losses: int
    win_rate: Decimal
    avg_win: Decimal
    avg_loss: Decimal
    avg_r: Optional[Decimal] = None
    expectancy_r: Optional[Decimal] = None
    total_pnl: Decimal
    best_trade: Optional[Decimal] = None
    worst_trade: Optional[Decimal] = None
    max_drawdown: Decimal

    @field_serializer(
        "win_rate",
        "avg_win",
        "avg_loss",
        "avg_r",
        "expectancy_r",
        "total_pnl",
        "best_trade",
        "worst_trade",
        "max_drawdown",
    )
    def serialize_optional_decimal(self, value: Optional[Decimal]) -> Optional[str]:
        return _optional_decimal_to_str(value)


class TagStatsBlock(JournalStatsBlock):
    """Stats for one setup tag."""

    tag: str


class CumulativePnlPoint(BaseModel):
    """One point on the cumulative P&L chart."""

    closed_at: datetime
    cumulative_pnl: Decimal

    @field_serializer("cumulative_pnl")
    def serialize_pnl(self, value: Decimal) -> str:
        return _decimal_to_str(value)


class ChecklistScoreGroupResponse(BaseModel):
    """Win-rate / expectancy slice for met vs below checklist score."""

    count: int
    win_rate: Decimal
    expectancy_r: Optional[Decimal] = None

    @field_serializer("win_rate", "expectancy_r")
    def serialize_optional_decimal(self, value: Optional[Decimal]) -> Optional[str]:
        return _optional_decimal_to_str(value)


class ChecklistScoreBreakdown(BaseModel):
    """Closed trades that met rules (score >= 70) vs those that did not."""

    met: ChecklistScoreGroupResponse
    below: ChecklistScoreGroupResponse


class JournalStatsResponse(BaseModel):
    """Journal dashboard payload."""

    overall: JournalStatsBlock
    by_tag: list[TagStatsBlock]
    cumulative_pnl: list[CumulativePnlPoint]
    by_checklist_score: ChecklistScoreBreakdown


class WatchlistCreateRequest(BaseModel):
    """Body for adding a watchlist symbol."""

    symbol: str = Field(..., min_length=1, max_length=32)
    notes: Optional[str] = Field(default=None, max_length=1000)

    @field_validator("symbol")
    @classmethod
    def _uppercase_symbol(cls, value: str) -> str:
        cleaned = value.strip().upper()
        if not cleaned:
            raise ValueError("symbol must not be empty")
        return cleaned


class WatchlistItemResponse(BaseModel):
    """A persisted watchlist item."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    symbol: str
    added_at: datetime
    notes: Optional[str] = None


class ScannerResultItem(BaseModel):
    """One symbol that passed scanner filters."""

    symbol: str
    last_price: Decimal
    gap_percent: Decimal
    relative_volume: Decimal
    avg_daily_volume: Decimal
    today_volume: int
    has_recent_news: Optional[bool] = None
    count_last_24h: Optional[int] = None
    next_earnings_date: Optional[date] = None
    days_until_earnings: Optional[int] = None
    earnings_risk: Optional[str] = None

    @field_serializer(
        "last_price",
        "gap_percent",
        "relative_volume",
        "avg_daily_volume",
    )
    def serialize_decimals(self, value: Decimal) -> str:
        return _decimal_to_str(value)


class ScannerErrorItem(BaseModel):
    """Per-symbol scan failure that does not abort the whole scan."""

    symbol: str
    error: str


class ScannerExcludedItem(ScannerResultItem):
    """Symbol that was scanned successfully but failed one or more filters."""

    reason: str


class ScannerResponse(BaseModel):
    """Scanner payload: matches, filter exclusions, and isolated errors."""

    scanned: int
    results: list[ScannerResultItem]
    excluded: list[ScannerExcludedItem]
    errors: list[ScannerErrorItem]


class IntradayBarResponse(BaseModel):
    """One intraday OHLCV bar."""

    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int

    @field_serializer("open", "high", "low", "close")
    def serialize_prices(self, value: Decimal) -> str:
        return _decimal_to_str(value)


class KeyLevelsResponse(BaseModel):
    """Key reference prices for the chart and summary panel."""

    prev_day_high: Optional[Decimal] = None
    prev_day_low: Optional[Decimal] = None
    prev_day_close: Optional[Decimal] = None
    today_open: Optional[Decimal] = None

    @field_serializer(
        "prev_day_high",
        "prev_day_low",
        "prev_day_close",
        "today_open",
    )
    def serialize_optional_price(self, value: Optional[Decimal]) -> Optional[str]:
        if value is None:
            return None
        return _decimal_to_str(value)


class TickerDetailResponse(BaseModel):
    """Ticker detail payload for the chart page."""

    symbol: str
    timeframe: str
    last_price: Decimal
    bars: list[IntradayBarResponse]
    vwap: list[Decimal]
    levels: KeyLevelsResponse
    sma_20: Optional[Decimal] = None
    sma_50: Optional[Decimal] = None
    gap_percent: Optional[Decimal] = None
    next_earnings_date: Optional[date] = None
    days_until_earnings: Optional[int] = None
    earnings_risk: Optional[str] = None
    earnings_time_of_day: Optional[str] = None

    @field_serializer("last_price", "sma_20", "sma_50", "gap_percent")
    def serialize_optional_money(self, value: Optional[Decimal]) -> Optional[str]:
        if value is None:
            return None
        return _decimal_to_str(value)

    @field_serializer("vwap")
    def serialize_vwap(self, value: list[Decimal]) -> list[str]:
        return [_decimal_to_str(item) for item in value]


class NewsItemResponse(BaseModel):
    """Headline-level news item for the ticker page."""

    id: str
    headline: str
    summary: str
    source: str
    url: str
    created_at: datetime
    symbols: list[str]


class TickerEarningsResponse(BaseModel):
    """Next earnings event and proximity risk for a ticker."""

    symbol: str
    next_earnings_date: Optional[date] = None
    days_until_earnings: Optional[int] = None
    earnings_risk: str
    time_of_day: Optional[str] = None
    eps_estimate: Optional[Decimal] = None

    @field_serializer("eps_estimate")
    def serialize_eps(self, value: Optional[Decimal]) -> Optional[str]:
        if value is None:
            return None
        return _decimal_to_str(value)


class TickerNewsResponse(BaseModel):
    """News feed payload for a symbol."""

    symbol: str
    items: list[NewsItemResponse]
    count_last_24h: int
    has_recent_news: bool


class ChecklistRuleInput(BaseModel):
    """One rule in a create/update checklist body."""

    position: int = 0
    label: str = Field(..., min_length=1, max_length=256)
    rule_type: str = Field(..., min_length=1, max_length=64)
    operator: str = Field(..., min_length=1, max_length=8)
    threshold: Optional[Decimal] = None
    required: bool = False

    @field_validator("threshold", mode="before")
    @classmethod
    def _coerce_threshold(cls, value):
        if value is None or value == "":
            return None
        return Decimal(str(value))


class ChecklistUpsertRequest(BaseModel):
    """Create or replace a checklist with its rules."""

    name: str = Field(..., min_length=1, max_length=128)
    description: Optional[str] = Field(default=None, max_length=1000)
    rules: list[ChecklistRuleInput] = Field(default_factory=list)


class ChecklistRuleResponse(BaseModel):
    """Persisted checklist rule."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    position: int
    label: str
    rule_type: str
    operator: str
    threshold: Optional[Decimal] = None
    required: bool

    @field_serializer("threshold")
    def serialize_threshold(self, value: Optional[Decimal]) -> Optional[str]:
        return _optional_decimal_to_str(value)


class ChecklistResponse(BaseModel):
    """Checklist with ordered rules."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: Optional[str] = None
    created_at: datetime
    rules: list[ChecklistRuleResponse]


class ChecklistEvaluateRequest(BaseModel):
    """Body for evaluating a checklist against a trade idea."""

    symbol: str = Field(..., min_length=1, max_length=32)
    entry: Decimal = Field(..., gt=0)
    stop: Decimal = Field(..., gt=0)
    target: Decimal = Field(..., gt=0)

    @field_validator("symbol")
    @classmethod
    def _uppercase_symbol(cls, value: str) -> str:
        cleaned = value.strip().upper()
        if not cleaned:
            raise ValueError("symbol must not be empty")
        return cleaned

    @field_validator("entry", "stop", "target", mode="before")
    @classmethod
    def _coerce_decimal(cls, value):
        return Decimal(str(value))


class ChecklistRuleResultResponse(BaseModel):
    """One evaluated rule row."""

    label: str
    passed: Optional[bool] = None
    actual: Optional[str] = None
    threshold: Optional[str] = None
    required: bool
    rule_type: str
    operator: str


class ChecklistEvaluateResponse(BaseModel):
    """Full evaluation payload."""

    checklist_id: int
    checklist_name: str
    results: list[ChecklistRuleResultResponse]
    score: int
    unknown_count: int
    required_failed: list[str]
    verdict: str


class BacktestCreateRequest(BaseModel):
    """Body for running a backtest."""

    symbols: Optional[list[str]] = None
    use_watchlist: bool = False
    start_date: date
    end_date: date
    name: Optional[str] = Field(default=None, max_length=256)
    min_gap_percent: Decimal = Field(default=Decimal("2"), ge=0)
    min_relative_volume: Decimal = Field(default=Decimal("2"), gt=0)
    min_price: Decimal = Field(default=Decimal("5"), gt=0)
    min_avg_volume: Decimal = Field(default=Decimal("500000"), ge=0)
    entry_rule: str = "break_prev_high"
    stop_rule: str = "fixed_percent"
    stop_percent: Decimal = Field(default=Decimal("2"), gt=0, lt=100)
    target_r: Decimal = Field(default=Decimal("2"), gt=0)
    cost_per_share: Decimal = Field(default=Decimal("0.02"), ge=0)
    risk_per_trade_percent: Decimal = Field(default=Decimal("1"), gt=0, le=100)
    starting_account: Decimal = Field(default=Decimal("10000"), gt=0)
    skip_earnings_days: int = Field(default=0, ge=0, le=30)

    @field_validator(
        "min_gap_percent",
        "min_relative_volume",
        "min_price",
        "min_avg_volume",
        "stop_percent",
        "target_r",
        "cost_per_share",
        "risk_per_trade_percent",
        "starting_account",
        mode="before",
    )
    @classmethod
    def _coerce_decimal(cls, value):
        if value is None:
            return value
        return Decimal(str(value))

    @field_validator("symbols", mode="before")
    @classmethod
    def _normalize_symbols(cls, value):
        if value is None:
            return None
        if isinstance(value, str):
            parts = [p.strip().upper() for p in value.split(",") if p.strip()]
            return parts
        return [str(v).strip().upper() for v in value if str(v).strip()]


