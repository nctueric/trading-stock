"""Simulated order matching engine for backtesting.

Fills market orders at the next bar's open ± slippage.
Fills limit orders when bar's high/low reaches the limit price.
"""

from __future__ import annotations

from collections import deque
from datetime import datetime
from decimal import Decimal
from typing import Callable, Optional

from txf.backtest.commission import CommissionModel
from txf.config.contracts import ContractRegistry
from txf.core.types import Bar, Fill, OrderRequest, PriceType, Side
from txf.position.calculator import calculate_notional_value


class MatchingEngine:
    """Simulates order matching against bar data.

    Key behaviors:
    - MARKET orders are queued and filled on the NEXT bar's open
      (to avoid look-ahead bias).
    - LIMIT BUY orders fill when bar.low <= limit price.
    - LIMIT SELL orders fill when bar.high >= limit price.
    - Slippage is applied to market order fills.
    """

    def __init__(
        self,
        contract_registry: ContractRegistry,
        commission_model: CommissionModel,
        slippage_ticks: int = 1,
    ) -> None:
        self._contracts = contract_registry
        self._commission = commission_model
        self._slippage_ticks = slippage_ticks
        self._pending_orders: deque[OrderRequest] = deque()
        self._fill_callback: Optional[Callable[[Fill], None]] = None

    def set_fill_callback(self, callback: Callable[[Fill], None]) -> None:
        """Register callback for when an order is filled."""
        self._fill_callback = callback

    def submit_order(self, order: OrderRequest) -> None:
        """Add an order to the pending queue."""
        self._pending_orders.append(order)

    def cancel_order(self, order_id: str) -> bool:
        """Cancel a pending order by ID."""
        before = len(self._pending_orders)
        self._pending_orders = deque(
            o for o in self._pending_orders if o.id != order_id
        )
        return len(self._pending_orders) < before

    def on_bar(self, bar: Bar) -> list[Fill]:
        """Process pending orders against the current bar.

        Call this at the START of each bar processing step
        (before strategy.on_bar), so that orders from the previous
        bar get filled at this bar's open/high/low.
        """
        fills: list[Fill] = []
        remaining: deque[OrderRequest] = deque()

        for order in self._pending_orders:
            if order.symbol != bar.symbol:
                remaining.append(order)
                continue

            fill = self._try_fill(order, bar)
            if fill is not None:
                fills.append(fill)
                if self._fill_callback:
                    self._fill_callback(fill)
            else:
                remaining.append(order)

        self._pending_orders = remaining
        return fills

    @property
    def pending_count(self) -> int:
        return len(self._pending_orders)

    def _try_fill(self, order: OrderRequest, bar: Bar) -> Optional[Fill]:
        spec = self._contracts.get(order.symbol)

        if order.price_type == PriceType.MARKET:
            # Fill at bar's open ± slippage
            slippage = spec.tick_size * self._slippage_ticks
            if order.side == Side.BUY:
                fill_price = bar.open + slippage
            else:
                fill_price = bar.open - slippage
            return self._create_fill(order, fill_price, bar.datetime)

        elif order.price_type == PriceType.LIMIT and order.price is not None:
            limit = order.price
            if order.side == Side.BUY and bar.low <= limit:
                # Fill at limit price (best case)
                fill_price = min(limit, bar.open)
                return self._create_fill(order, fill_price, bar.datetime)
            elif order.side == Side.SELL and bar.high >= limit:
                fill_price = max(limit, bar.open)
                return self._create_fill(order, fill_price, bar.datetime)

        return None

    def _create_fill(
        self,
        order: OrderRequest,
        price: Decimal,
        timestamp: datetime,
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
