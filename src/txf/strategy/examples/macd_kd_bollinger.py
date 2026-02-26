"""Strategy E: MACD+KD 共振 + 布林通道位置評估.

改良方向: 原始 MACD+KD 不考慮價格相對位置，
可能在「價格已遠離均線」時追價進場，風險較高。
加入 Bollinger Band 位置評估：
- 做多: 價格不能已在上軌上方 (避免追高)，最好在中軌附近
- 做空: 價格不能已在下軌下方 (避免追低)，最好在中軌附近
- 出場: 觸及對向布林軌道時可考慮獲利了結

另加入「部位持有時間限制」:
- 超過 max_hold 根 K 線未達 TP → 市價平倉 (避免盤整耗損)

核心變化:
- 進場過濾: 價格在布林中軌附近 (middle ± band_width × entry_zone)
- 出場額外: 觸及對向 band 或持倉超時
"""

from __future__ import annotations

from datetime import timedelta as _td
from decimal import Decimal

from txf.core.types import Bar
from txf.strategy.base import Strategy
from txf.strategy.indicators import macd, kd, ema, bollinger_bands


class MACDKDBollinger(Strategy):
    """MACD+KD 共振 + 布林通道位置評估."""

    def __init__(
        self,
        macd_fast: int = 12,
        macd_slow: int = 26,
        macd_signal: int = 9,
        kd_k_period: int = 9,
        kd_d_period: int = 3,
        trend_ema_period: int = 60,
        bb_period: int = 20,
        bb_std: float = 2.0,
        entry_zone: float = 0.7,
        stop_loss_points: int = 30,
        take_profit_points: int = 50,
        max_hold_bars: int = 45,
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
        self._bb_period = bb_period
        self._bb_std = bb_std
        self._entry_zone = entry_zone
        self._sl = stop_loss_points
        self._tp = take_profit_points
        self._max_hold = max_hold_bars
        self._avoid_open = avoid_open_minutes
        self._avoid_close = avoid_close_minutes
        self._quantity = quantity

        self._entry_price: Decimal | None = None
        self._bars_held = 0

    def on_bar(self, bar: Bar) -> None:
        warmup = max(self._macd_slow + self._macd_signal, self._trend_period, self._bb_period) + 10
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
        bb_upper, bb_middle, bb_lower = bollinger_bands(close, self._bb_period, self._bb_std)

        hist_now = float(histogram.iloc[-1])
        hist_prev = float(histogram.iloc[-2])
        k_now, k_prev = float(k_val.iloc[-1]), float(k_val.iloc[-2])
        d_now, d_prev = float(d_val.iloc[-1]), float(d_val.iloc[-2])
        trend_now = float(trend_line.iloc[-1])
        price_now = bar.close
        price_f = float(price_now)
        upper = float(bb_upper.iloc[-1])
        middle = float(bb_middle.iloc[-1])
        lower = float(bb_lower.iloc[-1])
        band_width = upper - lower

        is_uptrend = price_f > trend_now
        is_downtrend = price_f < trend_now

        macd_bull = hist_prev <= 0 and hist_now > 0
        macd_bear = hist_prev >= 0 and hist_now < 0
        kd_golden = k_prev <= d_prev and k_now > d_now
        kd_death = k_prev >= d_prev and k_now < d_now

        # Bollinger position: where is price relative to bands?
        # 0.0 = at lower, 0.5 = at middle, 1.0 = at upper
        bb_pos = (price_f - lower) / band_width if band_width > 0 else 0.5

        # Entry zone check: for buy, price should be below middle + zone * half_band
        buy_zone_ok = bb_pos < (0.5 + self._entry_zone * 0.5)
        sell_zone_ok = bb_pos > (0.5 - self._entry_zone * 0.5)

        # -- Exit --
        if not self.ctx.is_flat:
            self._bars_held += 1

        if self.ctx.is_long and self._entry_price is not None:
            pnl = price_now - self._entry_price
            # Fixed SL/TP
            if pnl <= -self._sl or pnl >= self._tp:
                self.ctx.close_position()
                self._reset()
                return
            # Bollinger upper band take profit
            if price_f >= upper and float(pnl) > 0:
                self.ctx.close_position()
                self._reset()
                return
            # Time stop
            if self._bars_held >= self._max_hold:
                self.ctx.close_position()
                self._reset()
                return
            if kd_death and k_now > 70:
                self.ctx.close_position()
                self._reset()
                return

        elif self.ctx.is_short and self._entry_price is not None:
            pnl = self._entry_price - price_now
            if pnl <= -self._sl or pnl >= self._tp:
                self.ctx.close_position()
                self._reset()
                return
            # Bollinger lower band take profit
            if price_f <= lower and float(pnl) > 0:
                self.ctx.close_position()
                self._reset()
                return
            if self._bars_held >= self._max_hold:
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

        if is_uptrend and macd_bull and kd_golden and buy_zone_ok:
            self.ctx.buy(self._quantity)
            self._entry_price = price_now
            self._bars_held = 0

        elif is_downtrend and macd_bear and kd_death and sell_zone_ok:
            self.ctx.sell(self._quantity)
            self._entry_price = price_now
            self._bars_held = 0

    def _reset(self):
        self._entry_price = None
        self._bars_held = 0
