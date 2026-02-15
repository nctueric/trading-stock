"""Tests for the stop engine."""

from decimal import Decimal
from datetime import datetime

from txf.config.contracts import ContractRegistry
from txf.core.types import Bar, Position, SessionType, Side
from txf.risk.stops import StopConfig, StopEngine


def make_bar(high: int, low: int, close: int) -> Bar:
    return Bar(
        symbol="TX",
        datetime=datetime(2024, 1, 2, 9, 0),
        open=Decimal(str(close)),
        high=Decimal(str(high)),
        low=Decimal(str(low)),
        close=Decimal(str(close)),
        volume=1000,
        session=SessionType.DAY,
    )


def test_stop_loss_long_triggered():
    engine = StopEngine(
        StopConfig(stop_loss_points=100),
        ContractRegistry(),
    )
    pos = Position(
        symbol="TX", side=Side.BUY, quantity=1,
        avg_price=Decimal("20000"),
    )
    # Bar low hits 19900 = entry - 100, should trigger
    bar = make_bar(high=20050, low=19900, close=19950)
    order = engine.on_bar(bar, pos)
    assert order is not None
    assert order.side == Side.SELL
    assert order.quantity == 1


def test_stop_loss_long_not_triggered():
    engine = StopEngine(
        StopConfig(stop_loss_points=100),
        ContractRegistry(),
    )
    pos = Position(
        symbol="TX", side=Side.BUY, quantity=1,
        avg_price=Decimal("20000"),
    )
    # Bar low 19950 > 19900 threshold -> no trigger
    bar = make_bar(high=20100, low=19950, close=20050)
    order = engine.on_bar(bar, pos)
    assert order is None


def test_take_profit_short_triggered():
    engine = StopEngine(
        StopConfig(take_profit_points=100),
        ContractRegistry(),
    )
    pos = Position(
        symbol="TX", side=Side.SELL, quantity=1,
        avg_price=Decimal("20000"),
    )
    # Bar low hits 19900 = entry - 100 -> profit for short
    bar = make_bar(high=20050, low=19900, close=19950)
    order = engine.on_bar(bar, pos)
    assert order is not None
    assert order.side == Side.BUY


def test_time_stop_triggered():
    engine = StopEngine(
        StopConfig(time_stop_bars=10),
        ContractRegistry(),
    )
    pos = Position(
        symbol="TX", side=Side.BUY, quantity=1,
        avg_price=Decimal("20000"),
    )
    bar = make_bar(high=20100, low=19950, close=20050)
    # bars_held=10 >= time_stop_bars=10 -> trigger
    order = engine.on_bar(bar, pos, bars_held=10)
    assert order is not None


def test_trailing_stop():
    engine = StopEngine(
        StopConfig(trailing_stop_points=50),
        ContractRegistry(),
    )
    pos = Position(
        symbol="TX", side=Side.BUY, quantity=1,
        avg_price=Decimal("20000"),
    )
    # Bar 1: high=20030, extreme=20030, low=20010 > 20030-50=19980 -> no trigger
    bar1 = make_bar(high=20030, low=20010, close=20020)
    order = engine.on_bar(bar1, pos)
    assert order is None

    # Bar 2: high=20100, extreme=20100, low=20060 > 20100-50=20050 -> no trigger
    bar2 = make_bar(high=20100, low=20060, close=20080)
    order = engine.on_bar(bar2, pos)
    assert order is None

    # Bar 3: high=20090 (no update), low=20055 > 20100-50=20050 -> no trigger
    bar3 = make_bar(high=20090, low=20055, close=20070)
    order = engine.on_bar(bar3, pos)
    assert order is None

    # Bar 4: high=20080 (no update), low=20040 <= 20100-50=20050 -> trigger!
    bar4 = make_bar(high=20080, low=20040, close=20045)
    order = engine.on_bar(bar4, pos)
    assert order is not None


def test_no_stop_on_flat():
    engine = StopEngine(
        StopConfig(stop_loss_points=100),
        ContractRegistry(),
    )
    bar = make_bar(high=20100, low=19800, close=19900)
    order = engine.on_bar(bar, None)
    assert order is None
