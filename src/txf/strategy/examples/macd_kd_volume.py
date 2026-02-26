"""Strategy B: MACD+KD 共振 + 成交量確認.

改良方向: 原始 MACD+KD 不看成交量，可能在量縮時進場
導致假突破。加入成交量過濾：
- 進場時成交量必須 > 均量 × 倍數
- 量能不足的交叉訊號直接忽略
- 加入「量價背離」出場條件: 價格創新高但量萎縮 → 提前出場

核心變化:
- 進場額外條件: volume > SMA(volume, 20) × 1.2
- 出場額外條件: 價格持續但量遞減 3 根 K 線 → 提前平倉
"""

from __future__ import annotations

from datetime import timedelta as _td
from decimal import Decimal

from txf.core.types import Bar
from txf.strategy.base import Strategy
from txf.strategy.indicators import macd, kd, ema, sma


class MACDKDVolume(Strategy):
    """MACD+KD 共振 + 成交量確認."""

    def __init__(
        self,
        macd_fast: int = 12,
        macd_slow: int = 26,
        macd_signal: int = 9,
        kd_k_period: int = 9,
        kd_d_period: int = 3,
        trend_ema_period: int = 60,
        stop_loss_points: int = 30,
        take_profit_points: int = 50,
        volume_period: int = 20,
        volume_multiple: float = 1.2,
        volume_decay_bars: int = 3,
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
        self._sl = stop_loss_points
        self._tp = take_profit_points
        self._vol_period = volume_period
        self._vol_mult = volume_multiple
        self._decay_bars = volume_decay_bars
        self._avoid_open = avoid_open_minutes
        self._avoid_close = avoid_close_minutes
        self._quantity = quantity

        self._entry_price: Decimal | None = None

    def on_bar(self, bar: Bar) -> None:
        warmup = max(self._macd_slow + self._macd_signal, self._trend_period, self._vol_period) + 10
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
        volume = self.ctx.volume

        macd_line, signal_line, histogram = macd(close, self._macd_fast, self._macd_slow, self._macd_signal)
        k_val, d_val = kd(high, low, close, self._kd_k, self._kd_d)
        trend_line = ema(close, self._trend_period)
        avg_vol = sma(volume.astype(float), self._vol_period)

        hist_now = float(histogram.iloc[-1])
        hist_prev = float(histogram.iloc[-2])
        k_now, k_prev = float(k_val.iloc[-1]), float(k_val.iloc[-2])
        d_now, d_prev = float(d_val.iloc[-1]), float(d_val.iloc[-2])
        trend_now = float(trend_line.iloc[-1])
        price_now = bar.close
        current_vol = float(volume.iloc[-1])
        avg_vol_now = float(avg_vol.iloc[-1]) if not avg_vol.isna().iloc[-1] else 0

        is_uptrend = float(price_now) > trend_now
        is_downtrend = float(price_now) < trend_now

        macd_bull = hist_prev <= 0 and hist_now > 0
        macd_bear = hist_prev >= 0 and hist_now < 0
        kd_golden = k_prev <= d_prev and k_now > d_now
        kd_death = k_prev >= d_prev and k_now < d_now

        # Volume confirmation
        volume_ok = current_vol > avg_vol_now * self._vol_mult

        # Volume decay detection: volume decreasing for N consecutive bars
        vol_decaying = False
        if len(volume) >= self._decay_bars + 1:
            recent_vols = [float(volume.iloc[-i]) for i in range(1, self._decay_bars + 2)]
            vol_decaying = all(recent_vols[i] < recent_vols[i + 1] for i in range(self._decay_bars))

        # -- Exit --
        if self.ctx.is_long and self._entry_price is not None:
            pnl = price_now - self._entry_price
            if pnl <= -self._sl or pnl >= self._tp:
                self.ctx.close_position()
                self._entry_price = None
                return
            # Volume decay exit: price holding but volume dying
            if pnl > 0 and vol_decaying:
                self.ctx.close_position()
                self._entry_price = None
                return
            if kd_death and k_now > 70:
                self.ctx.close_position()
                self._entry_price = None
                return

        elif self.ctx.is_short and self._entry_price is not None:
            pnl = self._entry_price - price_now
            if pnl <= -self._sl or pnl >= self._tp:
                self.ctx.close_position()
                self._entry_price = None
                return
            if pnl > 0 and vol_decaying:
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

        if is_uptrend and macd_bull and kd_golden and volume_ok:
            self.ctx.buy(self._quantity)
            self._entry_price = price_now

        elif is_downtrend and macd_bear and kd_death and volume_ok:
            self.ctx.sell(self._quantity)
            self._entry_price = price_now
