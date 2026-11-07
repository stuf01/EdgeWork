"""Pure checklist evaluation helpers (no I/O)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Callable, Optional, Sequence

ALLOWED_OPERATORS = (">=", "<=", ">", "<", "==")

ZERO = Decimal("0")
ONE = Decimal("1")


ContextGetter = Callable[[dict[str, Any]], Any]


def _get(key: str) -> ContextGetter:
    def getter(context: dict[str, Any]) -> Any:
        return context.get(key)

    return getter


RULE_REGISTRY: dict[str, ContextGetter] = {
    "gap_percent": _get("gap_percent"),
    "relative_volume": _get("relative_volume"),
    "avg_daily_volume": _get("avg_daily_volume"),
    "last_price": _get("last_price"),
    "has_recent_news": _get("has_recent_news"),
    "price_above_vwap": _get("price_above_vwap"),
    "price_above_prev_day_high": _get("price_above_prev_day_high"),
    "price_above_prev_day_low": _get("price_above_prev_day_low"),
    "entry_above_sma_20": _get("entry_above_sma_20"),
    "entry_above_sma_50": _get("entry_above_sma_50"),
    "risk_reward": _get("risk_reward"),
    "spread_percent": _get("spread_percent"),
    "stop_distance_percent": _get("stop_distance_percent"),
    "days_to_earnings": _get("days_to_earnings"),
}


@dataclass(frozen=True)
class ChecklistRuleSpec:
    """Rule fields needed for evaluation (ORM-agnostic)."""

    label: str
    rule_type: str
    operator: str
    threshold: Optional[Decimal]
    required: bool = False


@dataclass(frozen=True)
class RuleResult:
    """One evaluated checklist rule."""

    label: str
    passed: Optional[bool]  # True / False / None (unknown)
    actual: Any
    threshold: Optional[Decimal]
    required: bool
    rule_type: str
    operator: str


@dataclass(frozen=True)
class ScoreResult:
    """Aggregate score and verdict for an evaluation."""

    score: int
    unknown_count: int
    required_failed: list[str]
    verdict: str


def evaluate(
    checklist_rules: Sequence[ChecklistRuleSpec],
    context: dict[str, Any],
) -> list[RuleResult]:
    """Evaluate each rule against context; missing values are unknown."""
    results: list[RuleResult] = []
    for rule in checklist_rules:
        getter = RULE_REGISTRY.get(rule.rule_type)
        if getter is None:
            results.append(
                RuleResult(
                    label=rule.label,
                    passed=None,
                    actual=None,
                    threshold=rule.threshold,
                    required=rule.required,
                    rule_type=rule.rule_type,
                    operator=rule.operator,
                )
            )
            continue
        actual = getter(context)
        if actual is None:
            # spread_percent (and any missing field) -> unknown, not a hard fail
            results.append(
                RuleResult(
                    label=rule.label,
                    passed=None,
                    actual=None,
                    threshold=rule.threshold,
                    required=rule.required,
                    rule_type=rule.rule_type,
                    operator=rule.operator,
                )
            )
            continue
        passed = _compare(actual, rule.operator, rule.threshold)
        results.append(
            RuleResult(
                label=rule.label,
                passed=passed,
                actual=actual,
                threshold=rule.threshold,
                required=rule.required,
                rule_type=rule.rule_type,
                operator=rule.operator,
            )
        )
    return results


def score(results: Sequence[RuleResult]) -> ScoreResult:
    """Percent of rules passed; unknown counts as not passed."""
    total = len(results)
    if total == 0:
        return ScoreResult(
            score=0,
            unknown_count=0,
            required_failed=[],
            verdict="Does not meet your rules",
        )

    passed_count = sum(1 for item in results if item.passed is True)
    unknown_count = sum(1 for item in results if item.passed is None)
    score_pct = int(round(100 * passed_count / total))
    required_failed = [
        item.label
        for item in results
        if item.required and item.passed is not True
    ]
    verdict = (
        "Meets your rules"
        if score_pct >= 70 and not required_failed
        else "Does not meet your rules"
    )
    return ScoreResult(
        score=score_pct,
        unknown_count=unknown_count,
        required_failed=required_failed,
        verdict=verdict,
    )


def _compare(
    actual: Any,
    operator: str,
    threshold: Optional[Decimal],
) -> Optional[bool]:
    if operator not in ALLOWED_OPERATORS:
        return None
    left = _to_comparable(actual)
    if left is None:
        return None
    if threshold is None and not isinstance(actual, bool):
        return None
    right = _to_comparable(threshold if threshold is not None else actual)
    if isinstance(actual, bool):
        # Bool rules: threshold 1/true means expect True, 0/false means False.
        expected = True
        if threshold is not None:
            expected = threshold != ZERO
        if operator == "==":
            return actual is expected
        if operator == "!=":  # not in allowed list; fall through
            return None
        # Numeric-style ops on bools via 0/1
        left = ONE if actual else ZERO
        right = ONE if expected else ZERO
    elif right is None:
        return None

    assert isinstance(left, Decimal)
    assert isinstance(right, Decimal)
    if operator == ">=":
        return left >= right
    if operator == "<=":
        return left <= right
    if operator == ">":
        return left > right
    if operator == "<":
        return left < right
    if operator == "==":
        return left == right
    return None


def _to_comparable(value: Any) -> Optional[Decimal]:
    if value is None:
        return None
    if isinstance(value, bool):
        return ONE if value else ZERO
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float, str)):
        try:
            return Decimal(str(value))
        except Exception:
            return None
    return None


def default_breakout_rules() -> list[dict[str, Any]]:
    """Seed rule definitions for the Breakout basics checklist."""
    return [
        {
            "position": 0,
            "label": "Gap percent",
            "rule_type": "gap_percent",
            "operator": ">=",
            "threshold": Decimal("2"),
            "required": True,
        },
        {
            "position": 1,
            "label": "Relative volume",
            "rule_type": "relative_volume",
            "operator": ">=",
            "threshold": Decimal("2"),
            "required": True,
        },
        {
            "position": 2,
            "label": "Has recent news",
            "rule_type": "has_recent_news",
            "operator": "==",
            "threshold": Decimal("1"),
            "required": False,
        },
        {
            "position": 3,
            "label": "Price above VWAP",
            "rule_type": "price_above_vwap",
            "operator": "==",
            "threshold": Decimal("1"),
            "required": False,
        },
        {
            "position": 4,
            "label": "Broken above yesterday's high",
            "rule_type": "price_above_prev_day_high",
            "operator": "==",
            "threshold": Decimal("1"),
            "required": False,
        },
        {
            "position": 5,
            "label": "Risk / reward",
            "rule_type": "risk_reward",
            "operator": ">=",
            "threshold": Decimal("2"),
            "required": True,
        },
        {
            "position": 6,
            "label": "Entry above SMA 20",
            "rule_type": "entry_above_sma_20",
            "operator": "==",
            "threshold": Decimal("1"),
            "required": False,
        },
        {
            "position": 7,
            "label": "Days to earnings",
            "rule_type": "days_to_earnings",
            "operator": ">=",
            "threshold": Decimal("2"),
            "required": True,
        },
    ]


def days_to_earnings_seed_rule() -> dict[str, Any]:
    """Rule to append to existing Breakout basics checklists if missing."""
    return {
        "position": 7,
        "label": "Days to earnings",
        "rule_type": "days_to_earnings",
        "operator": ">=",
        "threshold": Decimal("2"),
        "required": True,
    }
