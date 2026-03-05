"""Abstract Broker interface for order execution.

All broker implementations (paper, Shioaji, etc.) conform to this ABC,
enabling the same Strategy code to run in backtest, paper, and live modes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable, Optional

from txf.core.types import Fill, OrderRequest, OrderStatus


class Broker(ABC):
    """Abstract broker for submitting, cancelling, and tracking orders."""

    @abstractmethod
    def connect(self) -> None:
        """Establish connection to the broker."""

    @abstractmethod
    def disconnect(self) -> None:
        """Close connection to the broker."""

    @abstractmethod
    def submit_order(self, order: OrderRequest) -> str:
        """Submit an order. Returns the order ID."""

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """Cancel a pending order. Returns True if successful."""

    @abstractmethod
    def get_order_status(self, order_id: str) -> OrderStatus:
        """Query the status of an order."""

    @abstractmethod
    def set_fill_callback(self, callback: Callable[[Fill], None]) -> None:
        """Register a callback that fires when an order is filled."""

    @property
    def is_connected(self) -> bool:
        """Override to report connection status."""
        return False
