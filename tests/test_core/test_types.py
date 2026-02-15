"""Tests for core data types."""

from decimal import Decimal
from datetime import datetime

from txf.core.types import (
    Bar,
    Fill,
    OrderRequest,
    Position,
    PortfolioState,
    Side,
    PriceType,
    SessionType,
)


def test_side_opposite():
    assert Side.BUY.opposite == Side.SELL
    assert Side.SELL.opposite == Side.BUY


def test_bar_frozen():
    bar = Bar(
        symbol="TX",
        datetime=datetime(2024, 1, 1),
        open=Decimal("20000"),
        high=Decimal("20100"),
        low=Decimal("19900"),
        close=Decimal("20050"),
        volume=1000,
    )
    assert bar.symbol == "TX"
    assert bar.session == SessionType.DAY  # default


def test_position_properties():
    pos = Position(
        symbol="TX",
        side=Side.BUY,
        quantity=2,
        avg_price=Decimal("20000"),
    )
    assert pos.is_long is True
    assert pos.is_short is False


def test_portfolio_state_defaults():
    state = PortfolioState(cash=Decimal("1000000"))
    assert state.positions == {}
    assert state.total_equity == Decimal("0")
