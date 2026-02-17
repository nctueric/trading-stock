"""Tests for pre-trade risk checks."""

from decimal import Decimal

from txf.config.contracts import ContractRegistry
from txf.core.types import OrderRequest, PortfolioState, Position, PriceType, Side
from txf.risk.limits import LimitChecker
from txf.risk.pre_trade import PreTradeRiskCheck


def test_margin_check_passes():
    check = PreTradeRiskCheck(
        ContractRegistry(), LimitChecker(), max_daily_loss=Decimal("100000")
    )
    portfolio = PortfolioState(
        cash=Decimal("1000000"),
        total_equity=Decimal("1000000"),
        available_margin=Decimal("1000000"),
    )
    order = OrderRequest(
        id="001", symbol="TX", side=Side.BUY, quantity=1,
        price_type=PriceType.MARKET,
    )
    assert check.check(order, portfolio) is None


def test_margin_check_rejects():
    check = PreTradeRiskCheck(
        ContractRegistry(), LimitChecker(), max_daily_loss=Decimal("100000")
    )
    portfolio = PortfolioState(
        cash=Decimal("100000"),
        total_equity=Decimal("100000"),
        available_margin=Decimal("100000"),
    )
    # TX margin = 184000, but only 100000 available
    order = OrderRequest(
        id="001", symbol="TX", side=Side.BUY, quantity=1,
        price_type=PriceType.MARKET,
    )
    result = check.check(order, portfolio)
    assert result is not None
    assert "Insufficient margin" in result


def test_position_limit_rejects():
    check = PreTradeRiskCheck(
        ContractRegistry(),
        LimitChecker(max_position_contracts=5),
        max_daily_loss=Decimal("100000"),
    )
    portfolio = PortfolioState(
        cash=Decimal("5000000"),
        total_equity=Decimal("5000000"),
        available_margin=Decimal("5000000"),
        positions={
            "TX": Position(
                symbol="TX", side=Side.BUY, quantity=5,
                avg_price=Decimal("20000"),
            )
        },
    )
    order = OrderRequest(
        id="001", symbol="TX", side=Side.BUY, quantity=1,
        price_type=PriceType.MARKET,
    )
    result = check.check(order, portfolio)
    assert result is not None
    assert "Position limit" in result


def test_close_order_bypasses_margin():
    """Closing an existing position should not require additional margin."""
    check = PreTradeRiskCheck(
        ContractRegistry(), LimitChecker(), max_daily_loss=Decimal("100000")
    )
    portfolio = PortfolioState(
        cash=Decimal("50000"),
        total_equity=Decimal("50000"),
        available_margin=Decimal("50000"),
        positions={
            "TX": Position(
                symbol="TX", side=Side.BUY, quantity=1,
                avg_price=Decimal("20000"),
            )
        },
    )
    # Sell to close - should pass even with low margin
    order = OrderRequest(
        id="001", symbol="TX", side=Side.SELL, quantity=1,
        price_type=PriceType.MARKET,
    )
    assert check.check(order, portfolio) is None
