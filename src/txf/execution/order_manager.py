"""Order lifecycle management.

Tracks all orders from submission to fill/cancel/expiry,
providing a unified view of order state regardless of broker.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Optional

from txf.core.types import Fill, OrderRequest, OrderStatus, Side

logger = logging.getLogger(__name__)


@dataclass
class OrderState:
    """Full lifecycle state for a single order."""

    order: OrderRequest
    status: OrderStatus = OrderStatus.PENDING
    fill: Optional[Fill] = None
    submitted_at: Optional[datetime] = None
    filled_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    reject_reason: str = ""


class OrderManager:
    """Manages order lifecycle tracking.

    Provides:
    - Order state lookup by ID
    - Pending/filled/cancelled order lists
    - Fill history
    """

    def __init__(self) -> None:
        self._orders: dict[str, OrderState] = {}
        self._fill_history: list[Fill] = []

    def register_order(self, order: OrderRequest) -> None:
        """Register a newly created order."""
        self._orders[order.id] = OrderState(
            order=order,
            status=OrderStatus.PENDING,
        )

    def mark_submitted(self, order_id: str, timestamp: Optional[datetime] = None) -> None:
        """Mark an order as submitted to the broker."""
        state = self._orders.get(order_id)
        if state:
            state.status = OrderStatus.SUBMITTED
            state.submitted_at = timestamp

    def mark_filled(self, fill: Fill) -> None:
        """Mark an order as filled and record the fill."""
        state = self._orders.get(fill.order_id)
        if state:
            state.status = OrderStatus.FILLED
            state.fill = fill
            state.filled_at = fill.timestamp
        self._fill_history.append(fill)
        logger.info(
            f"Order {fill.order_id} filled: {fill.side.value} "
            f"{fill.quantity}x {fill.symbol} @ {fill.price}"
        )

    def mark_cancelled(self, order_id: str, timestamp: Optional[datetime] = None) -> None:
        """Mark an order as cancelled."""
        state = self._orders.get(order_id)
        if state:
            state.status = OrderStatus.CANCELLED
            state.cancelled_at = timestamp

    def mark_rejected(self, order_id: str, reason: str) -> None:
        """Mark an order as rejected."""
        state = self._orders.get(order_id)
        if state:
            state.status = OrderStatus.FAILED
            state.reject_reason = reason
        logger.warning(f"Order {order_id} rejected: {reason}")

    def get_state(self, order_id: str) -> Optional[OrderState]:
        """Get the full state of an order."""
        return self._orders.get(order_id)

    def get_status(self, order_id: str) -> OrderStatus:
        """Get just the status of an order."""
        state = self._orders.get(order_id)
        return state.status if state else OrderStatus.FAILED

    @property
    def pending_orders(self) -> list[OrderState]:
        """All orders that are pending or submitted but not yet filled."""
        return [
            s for s in self._orders.values()
            if s.status in (OrderStatus.PENDING, OrderStatus.SUBMITTED)
        ]

    @property
    def filled_orders(self) -> list[OrderState]:
        """All filled orders."""
        return [
            s for s in self._orders.values()
            if s.status == OrderStatus.FILLED
        ]

    @property
    def fill_history(self) -> list[Fill]:
        """Chronological list of all fills."""
        return list(self._fill_history)

    @property
    def total_commission(self) -> Decimal:
        """Total commission paid across all fills."""
        return sum((f.commission for f in self._fill_history), Decimal("0"))

    @property
    def total_tax(self) -> Decimal:
        """Total tax paid across all fills."""
        return sum((f.tax for f in self._fill_history), Decimal("0"))

    def clear(self) -> None:
        """Reset all order tracking."""
        self._orders.clear()
        self._fill_history.clear()
