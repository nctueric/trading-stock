"""Tests for P&L calculator."""

from decimal import Decimal

from txf.core.types import Side
from txf.position.calculator import (
    calculate_unrealized_pnl,
    calculate_realized_pnl,
    calculate_margin_required,
    calculate_notional_value,
)
from txf.core.constants import TX_MULTIPLIER


def test_unrealized_pnl_long():
    # Long 1 TX at 20000, price now 20100 -> (100) * 1 * 200 = 20000
    pnl = calculate_unrealized_pnl(
        Side.BUY, Decimal("20000"), Decimal("20100"), 1, TX_MULTIPLIER
    )
    assert pnl == Decimal("20000")


def test_unrealized_pnl_short():
    # Short 1 TX at 20000, price now 19900 -> (20000-19900) * 1 * 200 = 20000
    pnl = calculate_unrealized_pnl(
        Side.SELL, Decimal("20000"), Decimal("19900"), 1, TX_MULTIPLIER
    )
    assert pnl == Decimal("20000")


def test_unrealized_pnl_long_losing():
    # Long 2 TX at 20000, price now 19950 -> (-50) * 2 * 200 = -20000
    pnl = calculate_unrealized_pnl(
        Side.BUY, Decimal("20000"), Decimal("19950"), 2, TX_MULTIPLIER
    )
    assert pnl == Decimal("-20000")


def test_realized_pnl():
    pnl = calculate_realized_pnl(
        Side.BUY, Decimal("20000"), Decimal("20200"), 1, TX_MULTIPLIER
    )
    assert pnl == Decimal("40000")  # 200 pts * 200 TWD


def test_margin_required(contract_registry):
    spec = contract_registry.get("TX")
    margin = calculate_margin_required(2, spec)
    assert margin == Decimal("368000")  # 184000 * 2


def test_notional_value():
    val = calculate_notional_value(Decimal("20000"), 1, TX_MULTIPLIER)
    assert val == Decimal("4000000")  # 20000 * 1 * 200
