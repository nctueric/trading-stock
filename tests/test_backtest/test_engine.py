"""Integration test for the BacktestEngine with DualMA strategy."""

from decimal import Decimal

from txf.backtest.engine import BacktestEngine
from txf.config.settings import BacktestSettings, RiskSettings
from txf.data.feed import HistoricalFeed
from txf.strategy.examples.dual_ma import DualMovingAverageCrossover


def test_backtest_runs_without_error(sample_bars):
    strategy = DualMovingAverageCrossover(fast=5, slow=20, quantity=1)
    feed = HistoricalFeed(sample_bars)
    settings = BacktestSettings(
        initial_capital=Decimal("1000000"),
        slippage_ticks=1,
    )
    engine = BacktestEngine(
        strategy=strategy,
        data_feed=feed,
        symbol="TX",
        backtest_settings=settings,
    )
    result = engine.run()

    assert result.total_bars == 100
    assert len(result.equity_curve) == 100
    assert result.initial_capital == Decimal("1000000")


def test_backtest_produces_fills(sample_bars):
    """With an up-then-down trend, dual MA should generate at least 1 fill."""
    strategy = DualMovingAverageCrossover(fast=3, slow=10, quantity=1)
    feed = HistoricalFeed(sample_bars)
    engine = BacktestEngine(
        strategy=strategy,
        data_feed=feed,
        symbol="TX",
        backtest_settings=BacktestSettings(
            initial_capital=Decimal("1000000"),
            slippage_ticks=0,
        ),
    )
    result = engine.run()
    # At minimum, the crossover should produce fills (open position)
    assert result.total_commission > 0  # At least one fill occurred
    # Equity should differ from initial capital (position has unrealized P&L)
    assert result.final_equity != result.initial_capital


def test_backtest_equity_curve_length(sample_bars):
    strategy = DualMovingAverageCrossover(fast=5, slow=20)
    feed = HistoricalFeed(sample_bars)
    engine = BacktestEngine(
        strategy=strategy,
        data_feed=feed,
        symbol="TX",
    )
    result = engine.run()
    assert len(result.equity_curve) == len(sample_bars)
