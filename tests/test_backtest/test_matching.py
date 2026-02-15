"""Tests for the MatchingEngine."""

from decimal import Decimal
from datetime import datetime

from txf.backtest.commission import CommissionModel
from txf.backtest.matching import MatchingEngine
from txf.config.contracts import ContractRegistry
from txf.core.types import Bar, OrderRequest, PriceType, SessionType, Side


def make_bar(open_p: int, high: int, low: int, close: int) -> Bar:
    return Bar(
        symbol="TX",
        datetime=datetime(2024, 1, 2, 9, 0),
        open=Decimal(str(open_p)),
        high=Decimal(str(high)),
        low=Decimal(str(low)),
        close=Decimal(str(close)),
        volume=1000,
        session=SessionType.DAY,
    )


def test_market_order_fills_at_open_plus_slippage():
    engine = MatchingEngine(ContractRegistry(), CommissionModel(), slippage_ticks=1)
    order = OrderRequest(
        id="001", symbol="TX", side=Side.BUY, quantity=1,
        price_type=PriceType.MARKET,
    )
    engine.submit_order(order)
    bar = make_bar(20000, 20100, 19900, 20050)
    fills = engine.on_bar(bar)
    assert len(fills) == 1
    assert fills[0].price == Decimal("20001")  # open 20000 + 1 tick slippage


def test_market_sell_fills_at_open_minus_slippage():
    engine = MatchingEngine(ContractRegistry(), CommissionModel(), slippage_ticks=1)
    order = OrderRequest(
        id="001", symbol="TX", side=Side.SELL, quantity=1,
        price_type=PriceType.MARKET,
    )
    engine.submit_order(order)
    bar = make_bar(20000, 20100, 19900, 20050)
    fills = engine.on_bar(bar)
    assert len(fills) == 1
    assert fills[0].price == Decimal("19999")  # open 20000 - 1 tick


def test_limit_buy_fills_when_low_reaches():
    engine = MatchingEngine(ContractRegistry(), CommissionModel())
    order = OrderRequest(
        id="001", symbol="TX", side=Side.BUY, quantity=1,
        price_type=PriceType.LIMIT, price=Decimal("19950"),
    )
    engine.submit_order(order)
    # Bar low touches 19900 which is below limit 19950
    bar = make_bar(20000, 20100, 19900, 20050)
    fills = engine.on_bar(bar)
    assert len(fills) == 1
    assert fills[0].price == Decimal("19950")  # filled at limit


def test_limit_sell_fills_when_high_reaches():
    engine = MatchingEngine(ContractRegistry(), CommissionModel())
    order = OrderRequest(
        id="001", symbol="TX", side=Side.SELL, quantity=1,
        price_type=PriceType.LIMIT, price=Decimal("20050"),
    )
    engine.submit_order(order)
    bar = make_bar(20000, 20100, 19900, 20050)
    fills = engine.on_bar(bar)
    assert len(fills) == 1
    assert fills[0].price == Decimal("20050")


def test_limit_order_not_filled():
    engine = MatchingEngine(ContractRegistry(), CommissionModel())
    order = OrderRequest(
        id="001", symbol="TX", side=Side.BUY, quantity=1,
        price_type=PriceType.LIMIT, price=Decimal("19800"),
    )
    engine.submit_order(order)
    bar = make_bar(20000, 20100, 19900, 20050)  # low=19900 > 19800
    fills = engine.on_bar(bar)
    assert len(fills) == 0
    assert engine.pending_count == 1


def test_cancel_order():
    engine = MatchingEngine(ContractRegistry(), CommissionModel())
    order = OrderRequest(
        id="001", symbol="TX", side=Side.BUY, quantity=1,
        price_type=PriceType.MARKET,
    )
    engine.submit_order(order)
    assert engine.cancel_order("001") is True
    assert engine.pending_count == 0


def test_fill_callback():
    engine = MatchingEngine(ContractRegistry(), CommissionModel(), slippage_ticks=0)
    fills_received = []
    engine.set_fill_callback(lambda f: fills_received.append(f))
    order = OrderRequest(
        id="001", symbol="TX", side=Side.BUY, quantity=1,
        price_type=PriceType.MARKET,
    )
    engine.submit_order(order)
    bar = make_bar(20000, 20100, 19900, 20050)
    engine.on_bar(bar)
    assert len(fills_received) == 1
