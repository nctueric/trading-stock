"""Abstract base class for trading strategies."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional

from txf.core.types import Bar
from txf.strategy.context import StrategyContext


class Strategy(ABC):
    """Base class for all trading strategies.

    Subclasses must implement:
    - on_bar(bar): Called for each new bar with the StrategyContext available
                   via self.ctx.

    Optionally override:
    - on_init(): Called once before the first bar
    - on_stop(): Called after the last bar (or when the strategy is stopped)

    Use self.ctx to access bar history, position state, and submit orders:
        self.ctx.close        -> pd.Series of close prices
        self.ctx.is_flat      -> bool
        self.ctx.buy(qty)     -> submit buy order
        self.ctx.sell(qty)    -> submit sell order
    """

    def __init__(self, **params: Any) -> None:
        self.params = params
        self._ctx: Optional[StrategyContext] = None

    @property
    def ctx(self) -> StrategyContext:
        assert self._ctx is not None, "Strategy context not initialized"
        return self._ctx

    def bind_context(self, ctx: StrategyContext) -> None:
        """Bind the strategy context (called by the engine)."""
        self._ctx = ctx

    def on_init(self) -> None:
        """Called once before the first bar. Override for setup logic."""

    @abstractmethod
    def on_bar(self, bar: Bar) -> None:
        """Called for each new bar. Implement your trading logic here."""

    def on_stop(self) -> None:
        """Called after the last bar. Override for cleanup logic."""
