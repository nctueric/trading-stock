"""Tests for the unified runner."""

import os
import tempfile
from decimal import Decimal

import pytest

from txf.runner import run_backtest, run_paper, register_strategy, get_strategy
from txf.strategy.examples.dual_ma import DualMovingAverageCrossover


@pytest.fixture
def sample_csv(sample_bars):
    """Write sample bars to a temporary CSV file."""
    import csv

    fd, path = tempfile.mkstemp(suffix=".csv")
    os.close(fd)
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["datetime", "open", "high", "low", "close", "volume"])
        for bar in sample_bars:
            writer.writerow([
                bar.datetime.strftime("%Y-%m-%d %H:%M:%S"),
                str(bar.open),
                str(bar.high),
                str(bar.low),
                str(bar.close),
                bar.volume,
            ])
    yield path
    os.unlink(path)


def test_run_backtest(sample_csv):
    result = run_backtest(
        strategy_cls=DualMovingAverageCrossover,
        data_path=sample_csv,
        strategy_params={"fast": 5, "slow": 20},
        initial_capital=Decimal("1000000"),
    )
    assert result.total_bars == 100
    assert len(result.equity_curve) == 100


def test_run_paper(sample_csv):
    result = run_paper(
        strategy_cls=DualMovingAverageCrossover,
        data_path=sample_csv,
        strategy_params={"fast": 5, "slow": 20},
        initial_capital=Decimal("1000000"),
    )
    assert result.total_bars == 100
    assert len(result.equity_curve) == 100


def test_strategy_registry():
    register_strategy("test_strat", DualMovingAverageCrossover)
    cls = get_strategy("test_strat")
    assert cls is DualMovingAverageCrossover


def test_strategy_not_found():
    with pytest.raises(ValueError, match="Unknown strategy"):
        get_strategy("nonexistent_strategy_xyz")
