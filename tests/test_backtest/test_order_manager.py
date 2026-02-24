"""Tests for OrderManager."""

from datetime import datetime
from decimal import Decimal

from txf.core.types import Fill, OrderRequest, OrderStatus, PriceType, Side
from txf.execution.order_manager import OrderManager


def test_register_and_lookup():
    om = OrderManager()
    order = OrderRequest(
        id="001", symbol="TX", side=Side.BUY, quantity=1,
        price_type=PriceType.MARKET,
    )
    om.register_order(order)
    state = om.get_state("001")
    assert state is not None
    assert state.status == OrderStatus.PENDING


def test_lifecycle_flow():
    om = OrderManager()
    order = OrderRequest(
        id="001", symbol="TX", side=Side.BUY, quantity=1,
        price_type=PriceType.MARKET,
    )
    om.register_order(order)

    om.mark_submitted("001", datetime(2024, 1, 1, 9, 0))
    assert om.get_status("001") == OrderStatus.SUBMITTED

    fill = Fill(
        order_id="001", symbol="TX", side=Side.BUY,
        price=Decimal("20000"), quantity=1,
        commission=Decimal("60"), tax=Decimal("8"),
        timestamp=datetime(2024, 1, 1, 9, 1),
    )
    om.mark_filled(fill)
    assert om.get_status("001") == OrderStatus.FILLED
    assert len(om.fill_history) == 1
    assert om.total_commission == Decimal("60")


def test_cancel_flow():
    om = OrderManager()
    order = OrderRequest(
        id="001", symbol="TX", side=Side.BUY, quantity=1,
        price_type=PriceType.LIMIT, price=Decimal("19900"),
    )
    om.register_order(order)
    om.mark_submitted("001")
    om.mark_cancelled("001")
    assert om.get_status("001") == OrderStatus.CANCELLED


def test_reject_flow():
    om = OrderManager()
    order = OrderRequest(
        id="001", symbol="TX", side=Side.BUY, quantity=1,
        price_type=PriceType.MARKET,
    )
    om.register_order(order)
    om.mark_rejected("001", "Insufficient margin")
    state = om.get_state("001")
    assert state is not None
    assert state.status == OrderStatus.FAILED
    assert state.reject_reason == "Insufficient margin"


def test_pending_and_filled_lists():
    om = OrderManager()
    for i in range(3):
        order = OrderRequest(
            id=f"00{i}", symbol="TX", side=Side.BUY, quantity=1,
            price_type=PriceType.MARKET,
        )
        om.register_order(order)
        om.mark_submitted(f"00{i}")

    assert len(om.pending_orders) == 3

    fill = Fill(
        order_id="001", symbol="TX", side=Side.BUY,
        price=Decimal("20000"), quantity=1,
        commission=Decimal("60"), tax=Decimal("8"),
        timestamp=datetime(2024, 1, 1, 9, 0),
    )
    om.mark_filled(fill)

    assert len(om.pending_orders) == 2
    assert len(om.filled_orders) == 1


def test_unknown_order_returns_failed():
    om = OrderManager()
    assert om.get_status("nonexistent") == OrderStatus.FAILED
