"""Strategy D: MACD+KD 自適應波動率策略.

改良方向: 原始 MACD+KD 的停損/停利是固定 30/50 點。
但市場波動率隨時間變化：
- 高波動期 (ATR 高): 需要更大的止損空間
- 低波動期 (ATR 低): 可以更精準的止損

本策略根據當前 ATR 相對歷史 ATR 的百分位動態調整：
- ATR 高 (>75th percentile): 放寬 SL=40, TP=65, 減少被震出
- ATR 中 (25-75th):          標準 SL=30, TP=50
- ATR 低 (<25th percentile): 收窄 SL=20, TP=35, 快進快出
- 額外: 低波動時跳過進場 (避免量價清淡的假訊號)

核心變化:
- 動態 SL/TP 根據 ATR percentile 分三級
- 低波動環境不開新倉
"""

from __future__ import annotations

from datetime import timedelta as _td
from decimal import Decimal

import numpy as np

from txf.core.types import Bar
from txf.strategy.base import Strategy
from txf.strategy.indicators import macd, kd, ema, atr


class MACDKDAdaptive(Strategy):
    """MACD+KD 自適應波動率策略."""

    def __init__(
        self,
        macd_fast: int = 12,
        macd_slow: int = 26,
        macd_signal: int = 9,
        kd_k_period: int = 9,
        kd_d_period: int = 3,
        trend_ema_period: int = 60,
        atr_period: int = 14,
        atr_lookback: int = 100,
        sl_high: int = 40,
        tp_high: int = 65,
        sl_mid: int = 30,
        tp_mid: int = 50,
        sl_low: int = 20,
        tp_low: int = 35,
        low_vol_skip: bool = True,
        avoid_open_minutes: int = 15,
        avoid_close_minutes: int = 15,
        quantity: int = 1,
    ) -> None:
        super().__init__()
        self._macd_fast = macd_fast
        self._macd_slow = macd_slow
        self._macd_signal = macd_signal
        self._kd_k = kd_k_period
        self._kd_d = kd_d_period
        self._trend_period = trend_ema_period
        self._atr_period = atr_period
        self._atr_lookback = atr_lookback
        self._sl = [sl_low, sl_mid, sl_high]
        self._tp = [tp_low, tp_mid, tp_high]
        self._low_vol_skip = low_vol_skip
        self._avoid_open = avoid_open_minutes
        self._avoid_close = avoid_close_minutes
        self._quantity = quantity

        self._entry_price: Decimal | None = None
        self._current_sl: int = sl_mid
        self._current_tp: int = tp_mid

    def _get_vol_regime(self, atr_series) -> int:
        """0=low, 1=mid, 2=high based on ATR percentile."""
        clean = atr_series.dropna()
        if len(clean) < self._atr_lookback:
            return 1
        recent = clean.iloc[-self._atr_lookback:]
        current = float(clean.iloc[-1])
        pct = float((recent < current).sum()) / len(recent) * 100
        if pct < 25:
            return 0  # low
        elif pct > 75:
            return 2  # high
        return 1  # mid

    def on_bar(self, bar: Bar) -> None:
        warmup = max(self._macd_slow + self._macd_signal, self._trend_period,
                     self._atr_period, self._atr_lookback) + 10
        if self.ctx.bar_count < warmup:
            return

        bar_time = bar.datetime.time()
        _open_dt = bar.datetime.replace(hour=8, minute=45, second=0)
        _close_dt = bar.datetime.replace(hour=13, minute=45, second=0)
        avoid_start = (_open_dt + _td(minutes=self._avoid_open)).time()
        avoid_end = (_close_dt - _td(minutes=self._avoid_close)).time()
        in_window = avoid_start <= bar_time <= avoid_end

        close = self.ctx.close
        high = self.ctx.high
        low = self.ctx.low

        macd_line, signal_line, histogram = macd(close, self._macd_fast, self._macd_slow, self._macd_signal)
        k_val, d_val = kd(high, low, close, self._kd_k, self._kd_d)
        trend_line = ema(close, self._trend_period)
        atr_series = atr(high, low, close, self._atr_period)

        hist_now = float(histogram.iloc[-1])
        hist_prev = float(histogram.iloc[-2])
        k_now, k_prev = float(k_val.iloc[-1]), float(k_val.iloc[-2])
        d_now, d_prev = float(d_val.iloc[-1]), float(d_val.iloc[-2])
        trend_now = float(trend_line.iloc[-1])
        price_now = bar.close

        is_uptrend = float(price_now) > trend_now
        is_downtrend = float(price_now) < trend_now

        macd_bull = hist_prev <= 0 and hist_now > 0
        macd_bear = hist_prev >= 0 and hist_now < 0
        kd_golden = k_prev <= d_prev and k_now > d_now
        kd_death = k_prev >= d_prev and k_now < d_now

        vol_regime = self._get_vol_regime(atr_series)

        # -- Exit (use SL/TP from entry time) --
        if self.ctx.is_long and self._entry_price is not None:
            pnl = price_now - self._entry_price
            if pnl <= -self._current_sl or pnl >= self._current_tp:
                self.ctx.close_position()
                self._entry_price = None
                return
            if kd_death and k_now > 70:
                self.ctx.close_position()
                self._entry_price = None
                return

        elif self.ctx.is_short and self._entry_price is not None:
            pnl = self._entry_price - price_now
            if pnl <= -self._current_sl or pnl >= self._current_tp:
                self.ctx.close_position()
                self._entry_price = None
                return
            if kd_golden and k_now < 30:
                self.ctx.close_position()
                self._entry_price = None
                return

        # -- Entry --
        if not self.ctx.is_flat or not in_window:
            return

        # Skip low volatility if configured
        if self._low_vol_skip and vol_regime == 0:
            return

        # Set SL/TP for current regime
        self._current_sl = self._sl[vol_regime]
        self._current_tp = self._tp[vol_regime]

        if is_uptrend and macd_bull and kd_golden:
            self.ctx.buy(self._quantity)
            self._entry_price = price_now

        elif is_downtrend and macd_bear and kd_death:
            self.ctx.sell(self._quantity)
            self._entry_price = price_now
