"""Stop-loss, take-profit, and trailing stop engine."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from txf.config.contracts import ContractRegistry
from txf.core.types import Bar, OrderRequest, Position, PriceType, Side


@dataclass
class StopConfig:
    """Configuration for stop mechanisms."""

    stop_loss_points: Optional[int] = None
    take_profit_points: Optional[int] = None
    trailing_stop_points: Optional[int] = None
    time_stop_bars: Optional[int] = None


class StopEngine:
    """Manages stop-loss, take-profit, and trailing stop orders.

    Checks each bar to see if any stop condition is met,
    and returns OrderRequests to close positions.
    """

    def __init__(
        self,
        config: StopConfig,
        contract_registry: ContractRegistry,
    ) -> None:
        self._config = config
        self._contracts = contract_registry
        # Track highest/lowest since entry for trailing stops
        self._trailing_extremes: dict[str, Decimal] = {}

    def on_bar(
        self,
        bar: Bar,
        position: Optional[Position],
        bars_held: int = 0,
    ) -> Optional[OrderRequest]:
        """Check stop conditions and return a close order if triggered.

        Returns None if no stop is triggered.
        """
        if position is None or position.quantity == 0:
            self._trailing_extremes.pop(bar.symbol, None)
            return None

        # Update trailing extreme
        self._update_trailing(bar, position)

        # Check each stop type
        if self._check_stop_loss(bar, position):
            return self._close_order(bar.symbol, position)

        if self._check_take_profit(bar, position):
            return self._close_order(bar.symbol, position)

        if self._check_trailing_stop(bar, position):
            return self._close_order(bar.symbol, position)

        if self._check_time_stop(bars_held):
            return self._close_order(bar.symbol, position)

        return None

    def reset(self, symbol: str) -> None:
        """Clear trailing data for a symbol (call after position close)."""
        self._trailing_extremes.pop(symbol, None)

    def _check_stop_loss(self, bar: Bar, pos: Position) -> bool:
        pts = self._config.stop_loss_points
        if pts is None:
            return False
        if pos.is_long:
            return bar.low <= pos.avg_price - Decimal(pts)
        else:
            return bar.high >= pos.avg_price + Decimal(pts)

    def _check_take_profit(self, bar: Bar, pos: Position) -> bool:
        pts = self._config.take_profit_points
        if pts is None:
            return False
        if pos.is_long:
            return bar.high >= pos.avg_price + Decimal(pts)
        else:
            return bar.low <= pos.avg_price - Decimal(pts)

    def _check_trailing_stop(self, bar: Bar, pos: Position) -> bool:
        pts = self._config.trailing_stop_points
        if pts is None:
            return False
        extreme = self._trailing_extremes.get(bar.symbol)
        if extreme is None:
            return False
        if pos.is_long:
            return bar.low <= extreme - Decimal(pts)
        else:
            return bar.high >= extreme + Decimal(pts)

    def _check_time_stop(self, bars_held: int) -> bool:
        if self._config.time_stop_bars is None:
            return False
        return bars_held >= self._config.time_stop_bars

    def _update_trailing(self, bar: Bar, pos: Position) -> None:
        if self._config.trailing_stop_points is None:
            return
        current = self._trailing_extremes.get(bar.symbol)
        if pos.is_long:
            new_extreme = bar.high
            if current is None or new_extreme > current:
                self._trailing_extremes[bar.symbol] = new_extreme
        else:
            new_extreme = bar.low
            if current is None or new_extreme < current:
                self._trailing_extremes[bar.symbol] = new_extreme

    def _close_order(self, symbol: str, pos: Position) -> OrderRequest:
        return OrderRequest(
            id=f"stop_{uuid.uuid4()}",
            symbol=symbol,
            side=pos.side.opposite,
            quantity=pos.quantity,
            price_type=PriceType.MARKET,
        )
