"""Shared test fixtures."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from txf.config.contracts import ContractRegistry
from txf.config.settings import BacktestSettings, RiskSettings
from txf.core.events import EventBus
from txf.core.types import Bar, Fill, SessionType, Side
from txf.position.manager import PositionManager


@pytest.fixture
def event_bus():
    return EventBus()


@pytest.fixture
def contract_registry():
    return ContractRegistry()


@pytest.fixture
def position_manager(contract_registry):
    return PositionManager(
        initial_capital=Decimal("1000000"),
        contract_registry=contract_registry,
    )


@pytest.fixture
def sample_bars() -> list[Bar]:
    """100 bars: 0-49 trending up, 50-99 trending down."""
    bars = []
    base_dt = datetime(2024, 1, 2, 8, 46)
    price = Decimal("20000")

    for i in range(100):
        delta = Decimal("10") if i < 50 else Decimal("-10")
        o = price
        h = price + Decimal("30")
        l = price - Decimal("20")
        c = price + delta
        price = c

        bars.append(
            Bar(
                symbol="TX",
                datetime=base_dt + timedelta(minutes=i),
                open=o,
                high=h,
                low=l,
                close=c,
                volume=1000 + i * 10,
                session=SessionType.DAY,
            )
        )
    return bars


@pytest.fixture
def sample_fill() -> Fill:
    return Fill(
        order_id="test_001",
        symbol="TX",
        side=Side.BUY,
        price=Decimal("20000"),
        quantity=1,
        commission=Decimal("60"),
        tax=Decimal("8"),
        timestamp=datetime(2024, 1, 2, 9, 0),
    )


@pytest.fixture
def backtest_settings() -> BacktestSettings:
    return BacktestSettings(
        initial_capital=Decimal("1000000"),
        commission_per_contract=Decimal("60"),
        tax_rate=Decimal("0.00002"),
        slippage_ticks=1,
    )


@pytest.fixture
def risk_settings() -> RiskSettings:
    return RiskSettings(
        max_position_contracts=10,
        max_drawdown_pct=Decimal("0.10"),
        max_daily_loss=Decimal("100000"),
    )
