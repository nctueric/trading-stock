"""StrategyContext: the bridge between Strategy and the engine.

Strategies interact with the system exclusively through this context
object, which provides bar history, position queries, and order submission.
This abstraction allows the same strategy code to work in both backtest
and live trading modes.
"""

from __future__ import annotations

from collections import deque
from decimal import Decimal
from typing import TYPE_CHECKING, Callable, Optional

import pandas as pd

from txf.core.types import Bar, OrderRequest, PriceType, Side, Position

if TYPE_CHECKING:
    from txf.position.manager import PositionManager

import uuid


class StrategyContext:
    """Proxy object injected into every Strategy instance."""

    def __init__(
        self,
        symbol: str,
        position_manager: "PositionManager",
        order_callback: Callable[[OrderRequest], None],
        max_history: int = 500,
    ) -> None:
        self._symbol = symbol
        self._pm = position_manager
        self._order_callback = order_callback
        self._max_history = max_history

        # Bar history (deque for O(1) append and bounded memory)
        self._bars: deque[Bar] = deque(maxlen=max_history)

        # Pandas Series caches (rebuilt on access after new bar)
        self._cache_dirty = True
        self._open_s: Optional[pd.Series] = None
        self._high_s: Optional[pd.Series] = None
        self._low_s: Optional[pd.Series] = None
        self._close_s: Optional[pd.Series] = None
        self._volume_s: Optional[pd.Series] = None

    # -- Bar management (called by the engine) --

    def push_bar(self, bar: Bar) -> None:
        """Add a new bar to history (called by engine, not by strategy)."""
        self._bars.append(bar)
        self._cache_dirty = True

    @property
    def bars(self) -> list[Bar]:
        return list(self._bars)

    @property
    def bar_count(self) -> int:
        return len(self._bars)

    @property
    def current_bar(self) -> Optional[Bar]:
        return self._bars[-1] if self._bars else None

    # -- Price series for indicator calculations --

    def _rebuild_cache(self) -> None:
        if not self._cache_dirty:
            return
        bars = list(self._bars)
        self._open_s = pd.Series([float(b.open) for b in bars], dtype=float)
        self._high_s = pd.Series([float(b.high) for b in bars], dtype=float)
        self._low_s = pd.Series([float(b.low) for b in bars], dtype=float)
        self._close_s = pd.Series([float(b.close) for b in bars], dtype=float)
        self._volume_s = pd.Series([b.volume for b in bars], dtype=float)
        self._cache_dirty = False

    @property
    def open(self) -> pd.Series:
        self._rebuild_cache()
        assert self._open_s is not None
        return self._open_s

    @property
    def high(self) -> pd.Series:
        self._rebuild_cache()
        assert self._high_s is not None
        return self._high_s

    @property
    def low(self) -> pd.Series:
        self._rebuild_cache()
        assert self._low_s is not None
        return self._low_s

    @property
    def close(self) -> pd.Series:
        self._rebuild_cache()
        assert self._close_s is not None
        return self._close_s

    @property
    def volume(self) -> pd.Series:
        self._rebuild_cache()
        assert self._volume_s is not None
        return self._volume_s

    # -- Position queries --

    @property
    def position(self) -> Optional[Position]:
        """Current position for this strategy's symbol."""
        return self._pm.get_position(self._symbol)

    @property
    def is_flat(self) -> bool:
        pos = self.position
        return pos is None or pos.quantity == 0

    @property
    def is_long(self) -> bool:
        pos = self.position
        return pos is not None and pos.is_long and pos.quantity > 0

    @property
    def is_short(self) -> bool:
        pos = self.position
        return pos is not None and pos.is_short and pos.quantity > 0

    @property
    def position_size(self) -> int:
        pos = self.position
        return pos.quantity if pos else 0

    # -- Order submission --

    def buy(self, quantity: int = 1, price: Optional[Decimal] = None) -> str:
        """Submit a buy order. Returns order ID."""
        return self._submit(Side.BUY, quantity, price)

    def sell(self, quantity: int = 1, price: Optional[Decimal] = None) -> str:
        """Submit a sell order. Returns order ID."""
        return self._submit(Side.SELL, quantity, price)

    def close_position(self) -> Optional[str]:
        """Close the entire current position. Returns order ID or None."""
        pos = self.position
        if pos is None or pos.quantity == 0:
            return None
        side = pos.side.opposite
        return self._submit(side, pos.quantity, None)

    def _submit(
        self, side: Side, quantity: int, price: Optional[Decimal]
    ) -> str:
        price_type = PriceType.LIMIT if price is not None else PriceType.MARKET
        order = OrderRequest(
            id=str(uuid.uuid4()),
            symbol=self._symbol,
            side=side,
            quantity=quantity,
            price_type=price_type,
            price=price,
            timestamp=self.current_bar.datetime if self.current_bar else None,
        )
        self._order_callback(order)
        return order.id
