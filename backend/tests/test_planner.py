"""Unit tests for pure planner calculations."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.planner import calculate_plan


def test_required_happy_path() -> None:
    result = calculate_plan(
        Decimal("10000"),
        Decimal("1"),
        Decimal("40.00"),
        Decimal("39.50"),
        Decimal("41.50"),
    )
    assert result["max_risk_dollars"] == Decimal("100")
    assert result["risk_per_share"] == Decimal("0.50")
    assert result["shares"] == 200
    assert result["actual_risk_dollars"] == Decimal("100.00")
    assert result["reward_per_share"] == Decimal("1.50")
    assert result["potential_profit"] == Decimal("300.00")
    assert result["risk_reward_ratio"] == Decimal("3")
    assert result["position_cost"] == Decimal("8000.00")
    assert result["exceeds_account"] is False


def test_shares_round_down() -> None:
    # max risk = 100, risk/share = 0.40 -> 250 shares exactly; use 0.33 to force floor
    result = calculate_plan(
        Decimal("10000"),
        Decimal("1"),
        Decimal("10.00"),
        Decimal("9.67"),
        Decimal("11.00"),
    )
    # max_risk=100, risk_per_share=0.33 -> 100/0.33 = 303.03... -> 303 shares
    assert result["risk_per_share"] == Decimal("0.33")
    assert result["shares"] == 303
    assert result["actual_risk_dollars"] == Decimal("99.99")


def test_invalid_stop_ordering() -> None:
    with pytest.raises(ValueError, match="stop < entry < target"):
        calculate_plan(
            Decimal("10000"),
            Decimal("1"),
            Decimal("40.00"),
            Decimal("40.50"),
            Decimal("41.50"),
        )


def test_invalid_target_ordering() -> None:
    with pytest.raises(ValueError, match="stop < entry < target"):
        calculate_plan(
            Decimal("10000"),
            Decimal("1"),
            Decimal("40.00"),
            Decimal("39.50"),
            Decimal("39.00"),
        )


def test_zero_account_size() -> None:
    with pytest.raises(ValueError, match="account_size"):
        calculate_plan(
            Decimal("0"),
            Decimal("1"),
            Decimal("40.00"),
            Decimal("39.50"),
            Decimal("41.50"),
        )


def test_negative_entry() -> None:
    with pytest.raises(ValueError, match="entry"):
        calculate_plan(
            Decimal("10000"),
            Decimal("1"),
            Decimal("-40.00"),
            Decimal("39.50"),
            Decimal("41.50"),
        )


def test_risk_percent_over_100() -> None:
    with pytest.raises(ValueError, match="risk_percent"):
        calculate_plan(
            Decimal("10000"),
            Decimal("101"),
            Decimal("40.00"),
            Decimal("39.50"),
            Decimal("41.50"),
        )


def test_exceeds_account() -> None:
    result = calculate_plan(
        Decimal("1000"),
        Decimal("10"),
        Decimal("50.00"),
        Decimal("49.00"),
        Decimal("55.00"),
    )
    # max risk 100, risk/share 1 -> 100 shares, position cost 5000 > 1000
    assert result["shares"] == 100
    assert result["position_cost"] == Decimal("5000.00")
    assert result["exceeds_account"] is True
