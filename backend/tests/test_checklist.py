"""Unit tests for checklist evaluate / score helpers."""

from __future__ import annotations

from decimal import Decimal

from app.checklist import ChecklistRuleSpec, evaluate, score


def _rule(
    label: str,
    rule_type: str,
    operator: str,
    threshold: str | None,
    required: bool = False,
) -> ChecklistRuleSpec:
    return ChecklistRuleSpec(
        label=label,
        rule_type=rule_type,
        operator=operator,
        threshold=Decimal(threshold) if threshold is not None else None,
        required=required,
    )


def test_evaluate_all_pass() -> None:
    rules = [
        _rule("Gap", "gap_percent", ">=", "2", True),
        _rule("RVOL", "relative_volume", ">=", "2", True),
        _rule("News", "has_recent_news", "==", "1"),
        _rule("RR", "risk_reward", ">=", "2", True),
    ]
    context = {
        "gap_percent": Decimal("5"),
        "relative_volume": Decimal("3"),
        "has_recent_news": True,
        "risk_reward": Decimal("2.5"),
    }
    results = evaluate(rules, context)
    assert all(item.passed is True for item in results)
    scored = score(results)
    assert scored.score == 100
    assert scored.required_failed == []
    assert scored.verdict == "Meets your rules"


def test_required_rule_failing() -> None:
    rules = [
        _rule("Gap", "gap_percent", ">=", "2", True),
        _rule("RVOL", "relative_volume", ">=", "2", True),
        _rule("RR", "risk_reward", ">=", "2", True),
    ]
    context = {
        "gap_percent": Decimal("5"),
        "relative_volume": Decimal("1"),
        "risk_reward": Decimal("3"),
    }
    results = evaluate(rules, context)
    scored = score(results)
    assert scored.score == 67
    assert "RVOL" in scored.required_failed
    assert scored.verdict == "Does not meet your rules"


def test_unknown_values() -> None:
    rules = [
        _rule("Spread", "spread_percent", "<=", "1"),
        _rule("Gap", "gap_percent", ">=", "2", True),
    ]
    context = {"gap_percent": Decimal("3"), "spread_percent": None}
    results = evaluate(rules, context)
    assert results[0].passed is None
    assert results[1].passed is True
    scored = score(results)
    assert scored.unknown_count == 1
    assert scored.score == 50
    assert scored.verdict == "Does not meet your rules"


def test_boundary_exactly_at_threshold() -> None:
    rules = [
        _rule("Gap", "gap_percent", ">=", "2", True),
        _rule("RR", "risk_reward", ">=", "2", True),
    ]
    context = {"gap_percent": Decimal("2"), "risk_reward": Decimal("2")}
    results = evaluate(rules, context)
    assert results[0].passed is True
    assert results[1].passed is True
    scored = score(results)
    assert scored.score == 100
    assert scored.verdict == "Meets your rules"


def test_verdict_high_score_but_required_failed() -> None:
    rules = [
        _rule("A", "last_price", ">", "1"),
        _rule("B", "avg_daily_volume", ">", "1"),
        _rule("C", "relative_volume", ">", "1"),
        _rule("Req", "gap_percent", ">=", "10", True),
    ]
    context = {
        "last_price": Decimal("10"),
        "avg_daily_volume": Decimal("10"),
        "relative_volume": Decimal("10"),
        "gap_percent": Decimal("1"),
    }
    results = evaluate(rules, context)
    scored = score(results)
    assert scored.score == 75
    assert scored.required_failed == ["Req"]
    assert scored.verdict == "Does not meet your rules"


def test_verdict_meets_at_70() -> None:
    rules = [
        _rule("1", "last_price", ">", "1"),
        _rule("2", "last_price", ">", "1"),
        _rule("3", "last_price", ">", "1"),
        _rule("4", "last_price", ">", "1"),
        _rule("5", "last_price", ">", "1"),
        _rule("6", "last_price", ">", "1"),
        _rule("7", "last_price", ">", "1"),
        _rule("8", "relative_volume", ">=", "99"),
        _rule("9", "avg_daily_volume", ">=", "99"),
        _rule("Gap", "gap_percent", ">=", "1", True),
    ]
    context = {
        "last_price": Decimal("10"),
        "relative_volume": Decimal("1"),
        "avg_daily_volume": Decimal("1"),
        "gap_percent": Decimal("2"),
    }
    results = evaluate(rules, context)
    scored = score(results)
    # 8 of 10 pass = 80
    assert scored.score == 80
    assert scored.required_failed == []
    assert scored.verdict == "Meets your rules"
