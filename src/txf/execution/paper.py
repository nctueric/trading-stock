"""Paper broker: simulated order execution with live market data.

Fills market orders immediately at last known price + slippage.
Fills limit orders when the feed price crosses the limit.
Does NOT send real orders to any exchange.
"""

from __future__ import annotations

import uuid
from collections import deque
from dataclasses import replace
from datetime import datetime
from decimal import Decimal
from typing import Callable, Optional

from txf.backtest.commission import CommissionModel
from txf.config.contracts import ContractRegistry
from txf.core.types import (
    Bar,
    Fill,
    OrderRequest,
    OrderStatus,
    PriceType,
    Side,
)
from txf.execution.broker import Broker
from txf.execution.order_manager import OrderManager
from txf.position.calculator import calculate_notional_value


class PaperBroker(Broker):
    """Simulated broker for paper trading.

    Uses live market data feed prices but does not send real orders.

    Fill logic:
    - MARKET orders: filled immediately at last known price + slippage
    - LIMIT orders: filled when feed price crosses the limit
    - Maintains an internal queue of pending limit orders
    """

    def __init__(
        self,
        contract_registry: ContractRegistry,
        commission_model: Optional[CommissionModel] = None,
        slippage_ticks: int = 1,
    ) -> None:
        self._contracts = contract_registry
        self._commission = commission_model or CommissionModel()
        self._slippage_ticks = slippage_ticks
        self._order_manager = OrderManager()
        self._fill_callback: Optional[Callable[[Fill], None]] = None
        self._pending: deque[OrderRequest] = deque()
        self._last_prices: dict[str, Decimal] = {}
        self._connected = False

    def connect(self) -> None:
        self._connected = True

    def disconnect(self) -> None:
        self._connected = False
        self._pending.clear()

    @property
    def is_connected(self) -> bool:
        return self._connected

    def submit_order(self, order: OrderRequest) -> str:
        """Submit an order for paper execution."""
        self._order_manager.register_order(order)
        self._order_manager.mark_submitted(order.id)

        if order.price_type == PriceType.MARKET:
            last = self._last_prices.get(order.symbol)
            if last is not None:
                self._execute_market(order, last)
                return order.id

        # Queue for later fill
        self._pending.append(order)
        return order.id

    def cancel_order(self, order_id: str) -> bool:
        """Cancel a pending order."""
        before = len(self._pending)
        self._pending = deque(o for o in self._pending if o.id != order_id)
        removed = len(self._pending) < before
        if removed:
            self._order_manager.mark_cancelled(order_id)
        return removed

    def get_order_status(self, order_id: str) -> OrderStatus:
        return self._order_manager.get_status(order_id)

    def set_fill_callback(self, callback: Callable[[Fill], None]) -> None:
        self._fill_callback = callback

    @property
    def order_manager(self) -> OrderManager:
        return self._order_manager

    # -- Market data integration --

    def on_bar(self, bar: Bar) -> list[Fill]:
        """Process a new bar: update prices and check pending orders.

        Called by the live/paper engine for each incoming bar.
        Returns list of fills generated.
        """
        self._last_prices[bar.symbol] = bar.close
        fills: list[Fill] = []
        remaining: deque[OrderRequest] = deque()

        for order in self._pending:
            if order.symbol != bar.symbol:
                remaining.append(order)
                continue

            fill = self._try_fill_on_bar(order, bar)
            if fill is not None:
                fills.append(fill)
                self._order_manager.mark_filled(fill)
                if self._fill_callback:
                    self._fill_callback(fill)
            else:
                remaining.append(order)

        self._pending = remaining
        return fills

    def on_price_update(self, symbol: str, price: Decimal) -> None:
        """Process a tick-level price update for pending limit orders."""
        self._last_prices[symbol] = price
        remaining: deque[OrderRequest] = deque()

        for order in self._pending:
            if order.symbol != symbol:
                remaining.append(order)
                continue

            filled = False
            if order.price_type == PriceType.MARKET:
                self._execute_market(order, price)
                filled = True
            elif order.price_type == PriceType.LIMIT and order.price is not None:
                limit = order.price
                if order.side == Side.BUY and price <= limit:
                    self._execute_at(order, limit)
                    filled = True
                elif order.side == Side.SELL and price >= limit:
                    self._execute_at(order, limit)
                    filled = True

            if not filled:
                remaining.append(order)

        self._pending = remaining

    # -- Internal fill logic --

    def _try_fill_on_bar(self, order: OrderRequest, bar: Bar) -> Optional[Fill]:
        """Try to fill an order using bar data."""
        spec = self._contracts.get(order.symbol)

        if order.price_type == PriceType.MARKET:
            slippage = spec.tick_size * self._slippage_ticks
            fill_price = (
                bar.open + slippage if order.side == Side.BUY
                else bar.open - slippage
            )
            return self._create_fill(order, fill_price, bar.datetime)

        elif order.price_type == PriceType.LIMIT and order.price is not None:
            limit = order.price
            if order.side == Side.BUY and bar.low <= limit:
                fill_price = min(limit, bar.open)
                return self._create_fill(order, fill_price, bar.datetime)
            elif order.side == Side.SELL and bar.high >= limit:
                fill_price = max(limit, bar.open)
                return self._create_fill(order, fill_price, bar.datetime)

        return None

    def _execute_market(self, order: OrderRequest, price: Decimal) -> None:
        """Fill a market order at price + slippage."""
        spec = self._contracts.get(order.symbol)
        slippage = spec.tick_size * self._slippage_ticks
        fill_price = (
            price + slippage if order.side == Side.BUY
            else price - slippage
        )
        self._execute_at(order, fill_price)

    def _execute_at(self, order: OrderRequest, price: Decimal) -> None:
        """Create and dispatch a fill at a specific price."""
        fill = self._create_fill(order, price, datetime.now())
        self._order_manager.mark_filled(fill)
        if self._fill_callback:
            self._fill_callback(fill)

    def _create_fill(
        self, order: OrderRequest, price: Decimal, timestamp: datetime
    ) -> Fill:
        spec = self._contracts.get(order.symbol)
        notional = calculate_notional_value(price, order.quantity, spec.multiplier)
        return Fill(
            order_id=order.id,
            symbol=order.symbol,
            side=order.side,
            price=price,
            quantity=order.quantity,
            commission=self._commission.calculate_commission(order.quantity),
            tax=self._commission.calculate_tax(notional),
            timestamp=timestamp,
        )

    @property
    def pending_count(self) -> int:
        return len(self._pending)
