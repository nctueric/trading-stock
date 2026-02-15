"""Dual Moving Average Crossover strategy.

A classic trend-following strategy for reference and testing.

Logic:
- BUY when fast MA crosses above slow MA (golden cross)
- SELL when fast MA crosses below slow MA (death cross)
- Only hold one position at a time
"""

from __future__ import annotations

from txf.core.types import Bar
from txf.strategy.base import Strategy
from txf.strategy.indicators import sma


class DualMovingAverageCrossover(Strategy):
    """Dual SMA crossover strategy.

    Parameters:
        fast: Fast moving average period (default: 5)
        slow: Slow moving average period (default: 20)
        quantity: Number of contracts per trade (default: 1)
    """

    def __init__(
        self,
        fast: int = 5,
        slow: int = 20,
        quantity: int = 1,
    ) -> None:
        super().__init__(fast=fast, slow=slow, quantity=quantity)
        self._fast = fast
        self._slow = slow
        self._quantity = quantity

    def on_bar(self, bar: Bar) -> None:
        # Need enough bars for the slow MA
        if self.ctx.bar_count < self._slow + 1:
            return

        close = self.ctx.close
        fast_ma = sma(close, self._fast)
        slow_ma = sma(close, self._slow)

        # Current and previous MA values
        fast_now = fast_ma.iloc[-1]
        fast_prev = fast_ma.iloc[-2]
        slow_now = slow_ma.iloc[-1]
        slow_prev = slow_ma.iloc[-2]

        # Golden cross: fast crosses above slow
        if fast_prev <= slow_prev and fast_now > slow_now:
            if self.ctx.is_short:
                self.ctx.close_position()
            if self.ctx.is_flat:
                self.ctx.buy(self._quantity)

        # Death cross: fast crosses below slow
        elif fast_prev >= slow_prev and fast_now < slow_now:
            if self.ctx.is_long:
                self.ctx.close_position()
            if self.ctx.is_flat:
                self.ctx.sell(self._quantity)
