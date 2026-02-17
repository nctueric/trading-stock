"""Tests for PositionManager."""

from datetime import datetime
from decimal import Decimal

from txf.core.types import Fill, Side
from txf.position.manager import PositionManager


def test_new_open(position_manager: PositionManager):
    fill = Fill(
        order_id="001",
        symbol="TX",
        side=Side.BUY,
        price=Decimal("20000"),
        quantity=1,
        commission=Decimal("60"),
        tax=Decimal("8"),
        timestamp=datetime(2024, 1, 2, 9, 0),
    )
    position_manager.apply_fill(fill)
    pos = position_manager.get_position("TX")
    assert pos is not None
    assert pos.side == Side.BUY
    assert pos.quantity == 1
    assert pos.avg_price == Decimal("20000")


def test_add_to_position(position_manager: PositionManager):
    # Open 1 contract at 20000
    position_manager.apply_fill(Fill(
        order_id="001", symbol="TX", side=Side.BUY,
        price=Decimal("20000"), quantity=1,
        commission=Decimal("60"), tax=Decimal("8"),
        timestamp=datetime(2024, 1, 2, 9, 0),
    ))
    # Add 1 contract at 20100
    position_manager.apply_fill(Fill(
        order_id="002", symbol="TX", side=Side.BUY,
        price=Decimal("20100"), quantity=1,
        commission=Decimal("60"), tax=Decimal("8"),
        timestamp=datetime(2024, 1, 2, 9, 5),
    ))
    pos = position_manager.get_position("TX")
    assert pos is not None
    assert pos.quantity == 2
    assert pos.avg_price == Decimal("20050")  # weighted avg


def test_full_close(position_manager: PositionManager):
    # Open
    position_manager.apply_fill(Fill(
        order_id="001", symbol="TX", side=Side.BUY,
        price=Decimal("20000"), quantity=1,
        commission=Decimal("60"), tax=Decimal("8"),
        timestamp=datetime(2024, 1, 2, 9, 0),
    ))
    # Close
    position_manager.apply_fill(Fill(
        order_id="002", symbol="TX", side=Side.SELL,
        price=Decimal("20100"), quantity=1,
        commission=Decimal("60"), tax=Decimal("8"),
        timestamp=datetime(2024, 1, 2, 10, 0),
    ))
    assert position_manager.get_position("TX") is None
    # PnL = (20100 - 20000) * 1 * 200 = 20000
    records = position_manager.trade_records
    assert len(records) == 1
    assert records[0].pnl == Decimal("20000")


def test_reverse_position(position_manager: PositionManager):
    # Open long 1
    position_manager.apply_fill(Fill(
        order_id="001", symbol="TX", side=Side.BUY,
        price=Decimal("20000"), quantity=1,
        commission=Decimal("60"), tax=Decimal("8"),
        timestamp=datetime(2024, 1, 2, 9, 0),
    ))
    # Sell 2 -> close 1 long + open 1 short
    position_manager.apply_fill(Fill(
        order_id="002", symbol="TX", side=Side.SELL,
        price=Decimal("20100"), quantity=2,
        commission=Decimal("120"), tax=Decimal("16"),
        timestamp=datetime(2024, 1, 2, 10, 0),
    ))
    pos = position_manager.get_position("TX")
    assert pos is not None
    assert pos.side == Side.SELL
    assert pos.quantity == 1
    assert pos.avg_price == Decimal("20100")


def test_mark_to_market(position_manager: PositionManager):
    position_manager.apply_fill(Fill(
        order_id="001", symbol="TX", side=Side.BUY,
        price=Decimal("20000"), quantity=1,
        commission=Decimal("60"), tax=Decimal("8"),
        timestamp=datetime(2024, 1, 2, 9, 0),
    ))
    position_manager.mark_to_market("TX", Decimal("20100"))
    pos = position_manager.get_position("TX")
    assert pos is not None
    # (20100 - 20000) * 1 * 200 = 20000
    assert pos.unrealized_pnl == Decimal("20000")


def test_cash_deductions(position_manager: PositionManager):
    initial = position_manager.cash
    position_manager.apply_fill(Fill(
        order_id="001", symbol="TX", side=Side.BUY,
        price=Decimal("20000"), quantity=1,
        commission=Decimal("60"), tax=Decimal("8"),
        timestamp=datetime(2024, 1, 2, 9, 0),
    ))
    # Cash reduced by commission + tax
    assert position_manager.cash == initial - Decimal("68")
