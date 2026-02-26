"""Strategy A: MACD+KD 共振 + ATR 動態追蹤停損.

改良方向: 原始 MACD+KD 使用固定 30/50 點停損停利，
但市場波動並非固定。改用 ATR 倍數動態調整：
- 波動大時給更寬的停損空間 → 不被甩出去
- 波動小時收窄停損 → 快速止損
- 移動追蹤停利 → 讓利潤奔跑

核心變化:
- 停損 = entry ± 2.0 × ATR (動態)
- 停利改為追蹤停損: 浮盈超過 1.5×ATR 後啟動, trailing = 1.0×ATR
"""

from __future__ import annotations

from datetime import timedelta as _td
from decimal import Decimal

from txf.core.types import Bar
from txf.strategy.base import Strategy
from txf.strategy.indicators import macd, kd, ema, atr


class MACDKDTrailingATR(Strategy):
    """MACD+KD 共振 + ATR 動態追蹤停損."""

    def __init__(
        self,
        macd_fast: int = 12,
        macd_slow: int = 26,
        macd_signal: int = 9,
        kd_k_period: int = 9,
        kd_d_period: int = 3,
        trend_ema_period: int = 60,
        atr_period: int = 14,
        sl_atr_multiple: float = 2.0,
        trail_trigger_atr: float = 1.5,
        trail_distance_atr: float = 1.0,
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
        self._sl_atr = sl_atr_multiple
        self._trail_trigger = trail_trigger_atr
        self._trail_dist = trail_distance_atr
        self._avoid_open = avoid_open_minutes
        self._avoid_close = avoid_close_minutes
        self._quantity = quantity

        self._entry_price: Decimal | None = None
        self._entry_atr: float = 0.0
        self._highest_since_entry: Decimal = Decimal("0")
        self._lowest_since_entry: Decimal = Decimal("999999")
        self._trailing_active = False

    def on_bar(self, bar: Bar) -> None:
        warmup = max(self._macd_slow + self._macd_signal, self._trend_period, self._atr_period) + 10
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
        atr_val = float(atr(high, low, close, self._atr_period).iloc[-1])

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

        # -- Exit logic --
        if self.ctx.is_long and self._entry_price is not None:
            self._highest_since_entry = max(self._highest_since_entry, price_now)
            sl = Decimal(str(self._entry_atr * self._sl_atr))
            pnl = price_now - self._entry_price

            # Fixed stop loss
            if pnl <= -sl:
                self.ctx.close_position()
                self._reset()
                return

            # Trailing stop: activate when profit > trigger, then trail
            trigger = Decimal(str(self._entry_atr * self._trail_trigger))
            if pnl >= trigger:
                self._trailing_active = True
            if self._trailing_active:
                trail = Decimal(str(self._entry_atr * self._trail_dist))
                if price_now < self._highest_since_entry - trail:
                    self.ctx.close_position()
                    self._reset()
                    return

            if kd_death and k_now > 70:
                self.ctx.close_position()
                self._reset()
                return

        elif self.ctx.is_short and self._entry_price is not None:
            self._lowest_since_entry = min(self._lowest_since_entry, price_now)
            sl = Decimal(str(self._entry_atr * self._sl_atr))
            pnl = self._entry_price - price_now

            if pnl <= -sl:
                self.ctx.close_position()
                self._reset()
                return

            trigger = Decimal(str(self._entry_atr * self._trail_trigger))
            if pnl >= trigger:
                self._trailing_active = True
            if self._trailing_active:
                trail = Decimal(str(self._entry_atr * self._trail_dist))
                if price_now > self._lowest_since_entry + trail:
                    self.ctx.close_position()
                    self._reset()
                    return

            if kd_golden and k_now < 30:
                self.ctx.close_position()
                self._reset()
                return

        # -- Entry --
        if not self.ctx.is_flat or not in_window:
            return

        if is_uptrend and macd_bull and kd_golden:
            self.ctx.buy(self._quantity)
            self._entry_price = price_now
            self._entry_atr = atr_val
            self._highest_since_entry = price_now
            self._trailing_active = False

        elif is_downtrend and macd_bear and kd_death:
            self.ctx.sell(self._quantity)
            self._entry_price = price_now
            self._entry_atr = atr_val
            self._lowest_since_entry = price_now
            self._trailing_active = False

    def _reset(self):
        self._entry_price = None
        self._entry_atr = 0.0
        self._highest_since_entry = Decimal("0")
        self._lowest_since_entry = Decimal("999999")
        self._trailing_active = False
