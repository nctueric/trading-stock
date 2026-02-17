"""Tests for performance metrics calculation."""

from decimal import Decimal

from txf.core.types import Side, TradeRecord
from txf.reporting.metrics import calculate_metrics, format_metrics
from datetime import datetime


def test_total_return():
    equity = [Decimal("1000000"), Decimal("1010000"), Decimal("1020000")]
    metrics = calculate_metrics(
        equity, [], initial_capital=Decimal("1000000"), total_bars=3
    )
    assert metrics.total_return == 20000.0
    assert abs(metrics.total_return_pct - 2.0) < 0.01


def test_max_drawdown():
    equity = [
        Decimal("1000000"),
        Decimal("1100000"),  # peak
        Decimal("1000000"),  # 100k drawdown from 1100k
        Decimal("1050000"),
    ]
    metrics = calculate_metrics(
        equity, [], initial_capital=Decimal("1000000"), total_bars=4
    )
    assert abs(metrics.max_drawdown - 100000.0) < 1.0
    assert abs(metrics.max_drawdown_pct - 9.09) < 0.1  # 100k/1100k ≈ 9.09%


def test_trade_statistics():
    trades = [
        TradeRecord(
            symbol="TX", side=Side.BUY,
            entry_price=Decimal("20000"), exit_price=Decimal("20100"),
            quantity=1, entry_time=datetime(2024, 1, 1),
            exit_time=datetime(2024, 1, 2),
            pnl=Decimal("20000"), commission=Decimal("60"), tax=Decimal("8"),
        ),
        TradeRecord(
            symbol="TX", side=Side.BUY,
            entry_price=Decimal("20100"), exit_price=Decimal("20000"),
            quantity=1, entry_time=datetime(2024, 1, 3),
            exit_time=datetime(2024, 1, 4),
            pnl=Decimal("-20000"), commission=Decimal("60"), tax=Decimal("8"),
        ),
        TradeRecord(
            symbol="TX", side=Side.SELL,
            entry_price=Decimal("20000"), exit_price=Decimal("19900"),
            quantity=1, entry_time=datetime(2024, 1, 5),
            exit_time=datetime(2024, 1, 6),
            pnl=Decimal("20000"), commission=Decimal("60"), tax=Decimal("8"),
        ),
    ]
    equity = [Decimal("1000000")] * 10
    metrics = calculate_metrics(equity, trades, Decimal("1000000"), total_bars=10)
    assert metrics.total_trades == 3
    assert metrics.winning_trades == 2
    assert metrics.losing_trades == 1
    assert abs(metrics.win_rate - 66.67) < 0.1


def test_format_metrics():
    equity = [Decimal("1000000"), Decimal("1050000")]
    metrics = calculate_metrics(equity, [], Decimal("1000000"), total_bars=2)
    text = format_metrics(metrics)
    assert "BACKTEST PERFORMANCE REPORT" in text
    assert "Total Return" in text


def test_empty_equity():
    metrics = calculate_metrics([], [], Decimal("1000000"))
    assert metrics.total_return == 0.0
