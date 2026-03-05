"""RSI Mean Reversion Strategy with ATR Volatility Filter.

針對雙均線策略的核心缺陷設計：
1. 逆勢交易而非追漲殺跌 — 在超賣區買入、超買區賣出
2. ATR 波動率過濾 — 只在波動夠大（有利可圖）時進場
3. 冷卻機制 — 避免連續出手造成過度交易
4. 明確停利停損 — 用 ATR 倍數動態設定出場點

Logic:
- BUY: RSI < oversold (30) 且 ATR > threshold
- SELL: RSI > overbought (70) 且 ATR > threshold
- EXIT: RSI 回到中性區 (40-60) 或持倉超過 max_hold_bars
"""

from __future__ import annotations

from txf.core.types import Bar
from txf.strategy.base import Strategy
from txf.strategy.indicators import rsi, atr, sma


class RSIMeanReversion(Strategy):
    """RSI 均值回歸策略.

    Parameters:
        rsi_period: RSI 計算週期 (default: 14)
        oversold: 超賣閾值 (default: 30)
        overbought: 超買閾值 (default: 70)
        exit_low: 多單出場閾值 (default: 45)
        exit_high: 空單出場閾值 (default: 55)
        atr_period: ATR 計算週期 (default: 14)
        atr_min_multiple: ATR 最小倍數過濾 (default: 0.5)
        cooldown_bars: 出場後冷卻期 (default: 10)
        max_hold_bars: 最大持倉 K 線數 (default: 60)
        quantity: 每次交易口數 (default: 1)
    """

    def __init__(
        self,
        rsi_period: int = 14,
        oversold: float = 30,
        overbought: float = 70,
        exit_low: float = 45,
        exit_high: float = 55,
        atr_period: int = 14,
        atr_min_multiple: float = 0.5,
        cooldown_bars: int = 10,
        max_hold_bars: int = 60,
        quantity: int = 1,
    ) -> None:
        super().__init__(
            rsi_period=rsi_period, oversold=oversold, overbought=overbought,
            exit_low=exit_low, exit_high=exit_high, atr_period=atr_period,
            atr_min_multiple=atr_min_multiple, cooldown_bars=cooldown_bars,
            max_hold_bars=max_hold_bars, quantity=quantity,
        )
        self._rsi_period = rsi_period
        self._oversold = oversold
        self._overbought = overbought
        self._exit_low = exit_low
        self._exit_high = exit_high
        self._atr_period = atr_period
        self._atr_min_multiple = atr_min_multiple
        self._cooldown = cooldown_bars
        self._max_hold = max_hold_bars
        self._quantity = quantity

        self._bars_since_exit = 999  # start ready to trade
        self._bars_in_position = 0

    def on_bar(self, bar: Bar) -> None:
        warmup = max(self._rsi_period, self._atr_period) + 2
        if self.ctx.bar_count < warmup:
            return

        close = self.ctx.close
        high = self.ctx.high
        low = self.ctx.low

        rsi_val = rsi(close, self._rsi_period).iloc[-1]
        atr_val = atr(high, low, close, self._atr_period).iloc[-1]
        atr_avg = sma(atr(high, low, close, self._atr_period).dropna(), 50)
        atr_threshold = atr_avg.iloc[-1] * self._atr_min_multiple if len(atr_avg.dropna()) > 0 else 0

        # Track position duration
        if not self.ctx.is_flat:
            self._bars_in_position += 1
        else:
            self._bars_since_exit += 1

        # -- Exit logic (priority) --
        if self.ctx.is_long:
            if rsi_val >= self._exit_low or self._bars_in_position >= self._max_hold:
                self.ctx.close_position()
                self._bars_in_position = 0
                self._bars_since_exit = 0
                return

        elif self.ctx.is_short:
            if rsi_val <= self._exit_high or self._bars_in_position >= self._max_hold:
                self.ctx.close_position()
                self._bars_in_position = 0
                self._bars_since_exit = 0
                return

        # -- Entry logic (only if flat + cooldown passed + ATR filter) --
        if not self.ctx.is_flat:
            return
        if self._bars_since_exit < self._cooldown:
            return
        if atr_val < atr_threshold:
            return

        if rsi_val < self._oversold:
            self.ctx.buy(self._quantity)
            self._bars_in_position = 0

        elif rsi_val > self._overbought:
            self.ctx.sell(self._quantity)
            self._bars_in_position = 0
