"""Tests for PaperBroker."""

from datetime import datetime
from decimal import Decimal

from txf.backtest.commission import CommissionModel
from txf.config.contracts import ContractRegistry
from txf.core.types import Bar, OrderRequest, OrderStatus, PriceType, SessionType, Side
from txf.execution.paper import PaperBroker


def _make_bar(open_p: int, high: int, low: int, close: int) -> Bar:
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


def test_connect_disconnect():
    broker = PaperBroker(ContractRegistry())
    assert not broker.is_connected
    broker.connect()
    assert broker.is_connected
    broker.disconnect()
    assert not broker.is_connected


def test_market_order_fills_on_bar():
    broker = PaperBroker(ContractRegistry(), slippage_ticks=1)
    broker.connect()

    order = OrderRequest(
        id="001", symbol="TX", side=Side.BUY, quantity=1,
        price_type=PriceType.MARKET,
    )
    broker.submit_order(order)
    assert broker.pending_count == 1

    bar = _make_bar(20000, 20100, 19900, 20050)
    fills = broker.on_bar(bar)
    assert len(fills) == 1
    assert fills[0].price == Decimal("20001")  # open + 1 tick slippage
    assert fills[0].side == Side.BUY
    assert broker.pending_count == 0


def test_market_order_immediate_fill_with_last_price():
    """Market order fills immediately if last price is known."""
    broker = PaperBroker(ContractRegistry(), slippage_ticks=1)
    broker.connect()

    # Set a known price first
    bar = _make_bar(20000, 20100, 19900, 20050)
    broker.on_bar(bar)  # sets last_price["TX"] = 20050

    fills = []
    broker.set_fill_callback(lambda f: fills.append(f))

    order = OrderRequest(
        id="002", symbol="TX", side=Side.SELL, quantity=1,
        price_type=PriceType.MARKET,
    )
    broker.submit_order(order)

    # Should fill immediately (not queued)
    assert len(fills) == 1
    assert fills[0].price == Decimal("20049")  # 20050 - 1 tick
    assert broker.pending_count == 0


def test_limit_buy_fills_on_bar():
    broker = PaperBroker(ContractRegistry())
    broker.connect()

    order = OrderRequest(
        id="001", symbol="TX", side=Side.BUY, quantity=1,
        price_type=PriceType.LIMIT, price=Decimal("19950"),
    )
    broker.submit_order(order)
    assert broker.pending_count == 1

    bar = _make_bar(20000, 20100, 19900, 20050)
    fills = broker.on_bar(bar)
    assert len(fills) == 1
    assert fills[0].price == Decimal("19950")


def test_limit_order_not_filled():
    broker = PaperBroker(ContractRegistry())
    broker.connect()

    order = OrderRequest(
        id="001", symbol="TX", side=Side.BUY, quantity=1,
        price_type=PriceType.LIMIT, price=Decimal("19800"),
    )
    broker.submit_order(order)

    bar = _make_bar(20000, 20100, 19900, 20050)
    fills = broker.on_bar(bar)
    assert len(fills) == 0
    assert broker.pending_count == 1


def test_cancel_order():
    broker = PaperBroker(ContractRegistry())
    broker.connect()

    order = OrderRequest(
        id="001", symbol="TX", side=Side.BUY, quantity=1,
        price_type=PriceType.LIMIT, price=Decimal("19800"),
    )
    broker.submit_order(order)
    assert broker.cancel_order("001") is True
    assert broker.pending_count == 0
    assert broker.get_order_status("001") == OrderStatus.CANCELLED


def test_order_manager_tracking():
    broker = PaperBroker(ContractRegistry(), slippage_ticks=0)
    broker.connect()

    order = OrderRequest(
        id="001", symbol="TX", side=Side.BUY, quantity=1,
        price_type=PriceType.MARKET,
    )
    broker.submit_order(order)

    bar = _make_bar(20000, 20100, 19900, 20050)
    broker.on_bar(bar)

    assert broker.get_order_status("001") == OrderStatus.FILLED
    assert len(broker.order_manager.fill_history) == 1
    assert broker.order_manager.total_commission > 0


def test_fill_callback():
    broker = PaperBroker(ContractRegistry(), slippage_ticks=0)
    broker.connect()

    received = []
    broker.set_fill_callback(lambda f: received.append(f))

    order = OrderRequest(
        id="001", symbol="TX", side=Side.BUY, quantity=1,
        price_type=PriceType.MARKET,
    )
    broker.submit_order(order)
    bar = _make_bar(20000, 20100, 19900, 20050)
    broker.on_bar(bar)

    assert len(received) == 1
    assert received[0].symbol == "TX"
