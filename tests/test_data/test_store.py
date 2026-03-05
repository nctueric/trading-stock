"""Tests for DataStore (SQLite persistence)."""

import os
import tempfile
from datetime import datetime
from decimal import Decimal

import pytest

from txf.core.types import Bar, SessionType, Side, TradeRecord
from txf.data.store import DataStore


@pytest.fixture
def tmp_db():
    """Create a temporary database file."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    os.unlink(path)


@pytest.fixture
def store(tmp_db):
    return DataStore(db_path=tmp_db)


def _make_bars(n: int, symbol: str = "TX") -> list[Bar]:
    bars = []
    for i in range(n):
        bars.append(
            Bar(
                symbol=symbol,
                datetime=datetime(2024, 1, 2, 8, 46 + i),
                open=Decimal("20000"),
                high=Decimal("20100"),
                low=Decimal("19900"),
                close=Decimal("20050"),
                volume=1000 + i,
                session=SessionType.DAY,
            )
        )
    return bars


def test_save_and_load_bars(store: DataStore):
    bars = _make_bars(5)
    saved = store.save_bars(bars)
    assert saved == 5

    loaded = store.load_bars("TX")
    assert len(loaded) == 5
    assert loaded[0].symbol == "TX"
    assert loaded[0].close == Decimal("20050")


def test_save_bars_dedup(store: DataStore):
    bars = _make_bars(3)
    store.save_bars(bars)
    # Save same bars again -> should skip duplicates
    saved_again = store.save_bars(bars)
    assert saved_again == 0
    assert store.count_bars("TX") == 3


def test_load_bars_date_filter(store: DataStore):
    bars = _make_bars(10)
    store.save_bars(bars)

    loaded = store.load_bars(
        "TX",
        start_date=datetime(2024, 1, 2, 8, 50),
        end_date=datetime(2024, 1, 2, 8, 53),
    )
    assert len(loaded) == 4  # minutes 50, 51, 52, 53


def test_count_bars(store: DataStore):
    store.save_bars(_make_bars(7))
    assert store.count_bars("TX") == 7
    assert store.count_bars("MTX") == 0


def test_get_date_range(store: DataStore):
    bars = _make_bars(5)
    store.save_bars(bars)

    first, last = store.get_date_range("TX")
    assert first == datetime(2024, 1, 2, 8, 46)
    assert last == datetime(2024, 1, 2, 8, 50)


def test_save_trades(store: DataStore):
    trades = [
        TradeRecord(
            symbol="TX",
            side=Side.BUY,
            entry_price=Decimal("20000"),
            exit_price=Decimal("20100"),
            quantity=1,
            entry_time=datetime(2024, 1, 2, 9, 0),
            exit_time=datetime(2024, 1, 2, 10, 0),
            pnl=Decimal("20000"),
            commission=Decimal("60"),
            tax=Decimal("8"),
            bars_held=60,
        )
    ]
    count = store.save_trades(trades, strategy_name="dual_ma", backtest_id="bt001")
    assert count == 1


def test_empty_db_returns_empty(store: DataStore):
    loaded = store.load_bars("TX")
    assert loaded == []
    first, last = store.get_date_range("TX")
    assert first is None
    assert last is None
