"""Unified entry point for backtest, paper trading, and live trading.

Usage:
    # Backtest mode
    python -m txf.runner --mode backtest --strategy dual_ma --data data/tx.csv

    # Paper trading mode
    python -m txf.runner --mode paper --strategy dual_ma

    # Programmatic usage
    from txf.runner import run_backtest, run_paper

    result = run_backtest(
        strategy_cls=DualMovingAverageCrossover,
        data_path="data/tx_1min.csv",
        strategy_params={"fast": 5, "slow": 20},
    )
"""

from __future__ import annotations

import argparse
import logging
import sys
from decimal import Decimal
from pathlib import Path
from typing import Optional, Type

from txf.backtest.engine import BacktestEngine, BacktestResult
from txf.config.contracts import ContractRegistry
from txf.config.settings import BacktestSettings, RiskSettings
from txf.data.feed import HistoricalFeed
from txf.data.fetchers.csv_loader import CsvLoader
from txf.reporting.metrics import calculate_metrics, format_metrics
from txf.strategy.base import Strategy

logger = logging.getLogger(__name__)


# -- Strategy registry (simple name-based lookup) --

_STRATEGY_REGISTRY: dict[str, Type[Strategy]] = {}


def register_strategy(name: str, cls: Type[Strategy]) -> None:
    """Register a strategy class for use with the runner."""
    _STRATEGY_REGISTRY[name] = cls


def get_strategy(name: str) -> Type[Strategy]:
    """Look up a registered strategy by name."""
    if name not in _STRATEGY_REGISTRY:
        _load_builtin_strategies()
    cls = _STRATEGY_REGISTRY.get(name)
    if cls is None:
        available = ", ".join(_STRATEGY_REGISTRY.keys()) or "(none)"
        raise ValueError(
            f"Unknown strategy '{name}'. Available: {available}"
        )
    return cls


def _load_builtin_strategies() -> None:
    """Lazy-load built-in example strategies."""
    from txf.strategy.examples.dual_ma import DualMovingAverageCrossover

    register_strategy("dual_ma", DualMovingAverageCrossover)

    try:
        from txf.strategy.examples.breakout import DonchianBreakout
        register_strategy("breakout", DonchianBreakout)
    except ImportError:
        pass


# -- Backtest runner --

def run_backtest(
    strategy_cls: Type[Strategy],
    data_path: str,
    symbol: str = "TX",
    strategy_params: Optional[dict] = None,
    initial_capital: Decimal = Decimal("1000000"),
    slippage_ticks: int = 1,
    risk_settings: Optional[RiskSettings] = None,
) -> BacktestResult:
    """Run a backtest and return results.

    Args:
        strategy_cls: Strategy class to instantiate.
        data_path: Path to CSV data file.
        symbol: Trading symbol (default "TX").
        strategy_params: Keyword arguments for strategy constructor.
        initial_capital: Starting capital in TWD.
        slippage_ticks: Slippage in ticks for market orders.
        risk_settings: Risk management settings.

    Returns:
        BacktestResult with equity curve, trades, and metrics.
    """
    params = strategy_params or {}
    strategy = strategy_cls(**params)

    # Load data
    loader = CsvLoader(symbol=symbol)
    bars = loader.load(data_path)
    if not bars:
        raise ValueError(f"No bars loaded from {data_path}")
    feed = HistoricalFeed(bars)

    # Settings
    bt_settings = BacktestSettings(
        initial_capital=initial_capital,
        slippage_ticks=slippage_ticks,
    )

    # Run
    engine = BacktestEngine(
        strategy=strategy,
        data_feed=feed,
        symbol=symbol,
        backtest_settings=bt_settings,
        risk_settings=risk_settings,
    )
    return engine.run()


# -- Paper trading runner --

def run_paper(
    strategy_cls: Type[Strategy],
    data_path: str,
    symbol: str = "TX",
    strategy_params: Optional[dict] = None,
    initial_capital: Decimal = Decimal("1000000"),
    slippage_ticks: int = 1,
    risk_settings: Optional[RiskSettings] = None,
) -> BacktestResult:
    """Run paper trading using historical data (offline paper mode).

    This is functionally identical to backtesting but uses the
    PaperBroker for order execution, demonstrating the full
    paper trading pipeline.

    For real-time paper trading with live data, use ShioajiBroker
    with simulation=True.
    """
    from txf.backtest.commission import CommissionModel
    from txf.execution.paper import PaperBroker
    from txf.position.manager import PositionManager
    from txf.risk.manager import RiskManager
    from txf.strategy.context import StrategyContext

    params = strategy_params or {}
    strategy = strategy_cls(**params)

    contracts = ContractRegistry()
    commission = CommissionModel()
    pm = PositionManager(initial_capital, contracts)
    risk = RiskManager(
        risk_settings=risk_settings or RiskSettings(),
        position_manager=pm,
        contract_registry=contracts,
    )
    broker = PaperBroker(contracts, commission, slippage_ticks)
    broker.connect()

    # Wire strategy context -> broker order submission
    def on_order(order):
        rejection = risk.check_pre_trade(order)
        if rejection:
            logger.warning(f"Order rejected: {rejection}")
            return
        broker.submit_order(order)

    ctx = StrategyContext(symbol, pm, on_order)
    strategy.bind_context(ctx)
    broker.set_fill_callback(lambda fill: pm.apply_fill(fill))

    # Load data and replay
    loader = CsvLoader(symbol=symbol)
    bars = loader.load(data_path)
    feed = HistoricalFeed(bars)

    strategy.on_init()
    bar_index = 0
    all_fills = []

    for bar in feed:
        pm.set_bar_index(bar_index)

        # Process pending orders from broker
        fills = broker.on_bar(bar)
        all_fills.extend(fills)

        # Mark to market
        pm.mark_to_market(bar.symbol, bar.close)

        # Risk checks
        risk_orders = risk.on_bar(bar)
        for order in risk_orders:
            broker.submit_order(order)

        # Strategy
        ctx.push_bar(bar)
        strategy.on_bar(bar)

        pm.snapshot_equity()
        bar_index += 1

    strategy.on_stop()
    broker.disconnect()

    total_commission = sum(f.commission for f in all_fills)
    total_tax = sum(f.tax for f in all_fills)

    return BacktestResult(
        equity_curve=pm.equity_curve,
        trade_records=pm.trade_records,
        final_equity=pm.total_equity,
        initial_capital=initial_capital,
        total_bars=bar_index,
        total_trades=len(pm.trade_records),
        total_commission=total_commission,
        total_tax=total_tax,
    )


# -- CLI entry point --

def main(argv: Optional[list[str]] = None) -> None:
    """CLI entry point for running strategies."""
    parser = argparse.ArgumentParser(
        description="TXF Quantitative Trading System"
    )
    parser.add_argument(
        "--mode",
        choices=["backtest", "paper"],
        default="backtest",
        help="Execution mode (default: backtest)",
    )
    parser.add_argument(
        "--strategy",
        required=True,
        help="Strategy name (e.g. dual_ma)",
    )
    parser.add_argument(
        "--data",
        required=True,
        help="Path to CSV data file",
    )
    parser.add_argument(
        "--symbol",
        default="TX",
        help="Trading symbol (default: TX)",
    )
    parser.add_argument(
        "--capital",
        type=float,
        default=1000000,
        help="Initial capital in TWD (default: 1000000)",
    )
    parser.add_argument(
        "--slippage",
        type=int,
        default=1,
        help="Slippage in ticks (default: 1)",
    )
    parser.add_argument(
        "--fast",
        type=int,
        default=None,
        help="Fast MA period (for dual_ma strategy)",
    )
    parser.add_argument(
        "--slow",
        type=int,
        default=None,
        help="Slow MA period (for dual_ma strategy)",
    )
    parser.add_argument(
        "--stop-loss",
        type=int,
        default=None,
        help="Stop loss in points",
    )
    parser.add_argument(
        "--take-profit",
        type=int,
        default=None,
        help="Take profit in points",
    )
    parser.add_argument(
        "--trailing-stop",
        type=int,
        default=None,
        help="Trailing stop in points",
    )
    parser.add_argument(
        "--max-contracts",
        type=int,
        default=10,
        help="Max position contracts (default: 10)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output HTML file for equity chart",
    )

    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    # Build strategy params
    strategy_params: dict = {}
    if args.fast is not None:
        strategy_params["fast"] = args.fast
    if args.slow is not None:
        strategy_params["slow"] = args.slow

    # Build risk settings
    risk_settings = RiskSettings(
        max_position_contracts=args.max_contracts,
        stop_loss_points=args.stop_loss,
        take_profit_points=args.take_profit,
        trailing_stop_points=args.trailing_stop,
    )

    # Get strategy class
    strategy_cls = get_strategy(args.strategy)

    # Run
    runner_fn = run_backtest if args.mode == "backtest" else run_paper
    result = runner_fn(
        strategy_cls=strategy_cls,
        data_path=args.data,
        symbol=args.symbol,
        strategy_params=strategy_params,
        initial_capital=Decimal(str(args.capital)),
        slippage_ticks=args.slippage,
        risk_settings=risk_settings,
    )

    # Report
    metrics = calculate_metrics(
        result.equity_curve,
        result.trade_records,
        result.initial_capital,
        result.total_commission,
        result.total_tax,
        result.total_bars,
    )
    print(format_metrics(metrics))

    # Optional chart
    if args.output:
        from txf.reporting.visualizer import plot_backtest_result

        plot_backtest_result(
            result.equity_curve,
            result.trade_records,
            title=f"{args.strategy} ({args.mode})",
            output_html=args.output,
        )
        print(f"\nChart saved to: {args.output}")


if __name__ == "__main__":
    main()
