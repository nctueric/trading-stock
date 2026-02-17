"""Backtest engine: the main event loop for historical replay."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from txf.backtest.commission import CommissionModel
from txf.backtest.matching import MatchingEngine
from txf.config.contracts import ContractRegistry
from txf.config.settings import BacktestSettings, RiskSettings
from txf.core.clock import SimulatedClock
from txf.core.events import EventBus, EventType
from txf.core.types import Bar, Fill, OrderRequest, TradeRecord
from txf.data.feed import DataFeed
from txf.position.manager import PositionManager
from txf.risk.manager import RiskManager
from txf.strategy.base import Strategy
from txf.strategy.context import StrategyContext


@dataclass
class BacktestResult:
    """Container for backtest output."""

    equity_curve: list[Decimal] = field(default_factory=list)
    trade_records: list[TradeRecord] = field(default_factory=list)
    final_equity: Decimal = Decimal("0")
    initial_capital: Decimal = Decimal("0")
    total_bars: int = 0
    total_trades: int = 0
    total_commission: Decimal = Decimal("0")
    total_tax: Decimal = Decimal("0")


class BacktestEngine:
    """Event-driven backtest engine.

    Main loop for each bar:
    1. Advance clock
    2. MatchingEngine processes pending orders (from previous bar)
    3. PositionManager.mark_to_market()
    4. RiskManager.on_bar() (check stops, drawdown, etc.)
    5. Push bar to StrategyContext
    6. Strategy.on_bar() (may submit new orders)
    7. New orders go through pre-trade risk check -> MatchingEngine queue
    8. Snapshot equity
    """

    def __init__(
        self,
        strategy: Strategy,
        data_feed: DataFeed,
        symbol: str = "TX",
        backtest_settings: Optional[BacktestSettings] = None,
        risk_settings: Optional[RiskSettings] = None,
        contract_registry: Optional[ContractRegistry] = None,
    ) -> None:
        self._bt_settings = backtest_settings or BacktestSettings()
        self._risk_settings = risk_settings or RiskSettings()
        self._contracts = contract_registry or ContractRegistry()

        self._strategy = strategy
        self._data_feed = data_feed
        self._symbol = symbol

        # Core components
        self._clock = SimulatedClock()
        self._event_bus = EventBus()
        self._commission = CommissionModel(
            self._bt_settings.commission_per_contract,
            self._bt_settings.tax_rate,
        )
        self._matching = MatchingEngine(
            self._contracts,
            self._commission,
            self._bt_settings.slippage_ticks,
        )
        self._position_mgr = PositionManager(
            self._bt_settings.initial_capital,
            self._contracts,
        )
        self._risk_mgr = RiskManager(
            risk_settings=self._risk_settings,
            position_manager=self._position_mgr,
            contract_registry=self._contracts,
        )

        # Strategy context
        self._ctx = StrategyContext(
            symbol=symbol,
            position_manager=self._position_mgr,
            order_callback=self._on_order_submitted,
        )
        self._strategy.bind_context(self._ctx)

        # Wire fill callback
        self._matching.set_fill_callback(self._on_fill)

        # Track all fills for reporting
        self._all_fills: list[Fill] = []

    def run(self) -> BacktestResult:
        """Execute the backtest and return results."""
        self._strategy.on_init()
        bar_index = 0

        for bar in self._data_feed:
            # 1. Advance clock
            self._clock.advance_to(bar.datetime)
            self._position_mgr.set_bar_index(bar_index)

            # 2. Process pending orders from previous bar
            fills = self._matching.on_bar(bar)
            self._all_fills.extend(fills)

            # 3. Mark to market
            self._position_mgr.mark_to_market(bar.symbol, bar.close)

            # 4. Risk checks (may generate close orders)
            risk_orders = self._risk_mgr.on_bar(bar)
            for order in risk_orders:
                self._matching.submit_order(order)

            # 5. Push bar to context
            self._ctx.push_bar(bar)

            # 6. Strategy logic
            self._strategy.on_bar(bar)

            # 7. Snapshot equity
            self._position_mgr.snapshot_equity()

            bar_index += 1

        self._strategy.on_stop()

        # Build result
        return self._build_result(bar_index)

    def _on_order_submitted(self, order: OrderRequest) -> None:
        """Called when strategy submits an order via context."""
        # Pre-trade risk check
        rejection = self._risk_mgr.check_pre_trade(order)
        if rejection is not None:
            self._event_bus.publish(
                EventType.ORDER_REJECTED,
                {"order": order, "reason": rejection},
            )
            return
        self._matching.submit_order(order)
        self._event_bus.publish(EventType.ORDER_SUBMITTED, order)

    def _on_fill(self, fill: Fill) -> None:
        """Called when an order is filled by the matching engine."""
        self._position_mgr.apply_fill(fill)
        self._event_bus.publish(EventType.ORDER_FILLED, fill)
        self._event_bus.publish(EventType.POSITION_CHANGED, fill.symbol)

    def _build_result(self, total_bars: int) -> BacktestResult:
        total_commission = sum(f.commission for f in self._all_fills)
        total_tax = sum(f.tax for f in self._all_fills)
        return BacktestResult(
            equity_curve=self._position_mgr.equity_curve,
            trade_records=self._position_mgr.trade_records,
            final_equity=self._position_mgr.total_equity,
            initial_capital=self._bt_settings.initial_capital,
            total_bars=total_bars,
            total_trades=len(self._position_mgr.trade_records),
            total_commission=total_commission,
            total_tax=total_tax,
        )
