"""Risk manager: orchestrates all risk control components."""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from txf.config.contracts import ContractRegistry
from txf.config.settings import RiskSettings
from txf.core.types import Bar, OrderRequest, PriceType
from txf.position.manager import PositionManager
from txf.risk.limits import LimitChecker
from txf.risk.pre_trade import PreTradeRiskCheck
from txf.risk.realtime import RealtimeRiskMonitor
from txf.risk.stops import StopConfig, StopEngine


class RiskManager:
    """Central risk management orchestrator.

    Coordinates:
    - Pre-trade risk checks (before order submission)
    - Stop engine (per-bar stop loss/profit/trailing checks)
    - Real-time monitoring (drawdown, margin, daily loss)
    """

    def __init__(
        self,
        risk_settings: RiskSettings,
        position_manager: PositionManager,
        contract_registry: ContractRegistry,
    ) -> None:
        self._pm = position_manager
        self._contracts = contract_registry
        self._settings = risk_settings

        # Sub-components
        self._limit_checker = LimitChecker(
            max_position_contracts=risk_settings.max_position_contracts,
        )
        self._pre_trade = PreTradeRiskCheck(
            contract_registry=contract_registry,
            limit_checker=self._limit_checker,
            max_daily_loss=risk_settings.max_daily_loss,
        )
        self._stop_engine = StopEngine(
            config=StopConfig(
                stop_loss_points=risk_settings.stop_loss_points,
                take_profit_points=risk_settings.take_profit_points,
                trailing_stop_points=risk_settings.trailing_stop_points,
                time_stop_bars=risk_settings.time_stop_bars,
            ),
            contract_registry=contract_registry,
        )
        self._realtime = RealtimeRiskMonitor(
            max_drawdown_pct=risk_settings.max_drawdown_pct,
            max_daily_loss=risk_settings.max_daily_loss,
        )
        self._initialized = False

    def check_pre_trade(self, order: OrderRequest) -> Optional[str]:
        """Run pre-trade risk check. Returns rejection reason or None."""
        if self._realtime.is_trading_halted:
            return "Trading halted due to risk breach"

        portfolio = self._pm.get_portfolio_state()
        self._pre_trade.update_daily_pnl(portfolio.realized_pnl)
        return self._pre_trade.check(order, portfolio)

    def on_bar(self, bar: Bar) -> list[OrderRequest]:
        """Per-bar risk checks. Returns list of orders to execute (e.g. stops).

        Called by the engine after mark_to_market but before strategy.on_bar.
        """
        if not self._initialized:
            self._realtime.initialize(self._pm.total_equity)
            self._initialized = True

        orders: list[OrderRequest] = []
        portfolio = self._pm.get_portfolio_state()

        # Real-time monitoring
        warnings = self._realtime.update(portfolio)
        if warnings:
            # If force close needed, generate close orders for all positions
            if self._realtime.should_force_close():
                for sym, pos in portfolio.positions.items():
                    close_order = OrderRequest(
                        id=f"risk_close_{sym}",
                        symbol=sym,
                        side=pos.side.opposite,
                        quantity=pos.quantity,
                        price_type=PriceType.MARKET,
                    )
                    orders.append(close_order)
                return orders

        # Stop engine checks
        for sym, pos in portfolio.positions.items():
            entry_bar = self._pm._entry_bar_index.get(sym, 0)
            bars_held = self._pm._current_bar_index - entry_bar
            stop_order = self._stop_engine.on_bar(bar, pos, bars_held)
            if stop_order is not None:
                orders.append(stop_order)

        return orders
