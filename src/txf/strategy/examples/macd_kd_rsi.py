"""Strategy C: MACD+KD 共振 + RSI 動能過濾.

改良方向: 原始 MACD+KD 進場時不看動能強度。
加入 RSI 過濾可避免在動能耗盡時進場：
- 做多時要求 RSI 在 40-65 區間 (不在超買也不在超弱)
- 做空時要求 RSI 在 35-60 區間 (不在超賣也不在超強)
- RSI 極端區 = 動能即將反轉，不宜追價

另加入「鬆弛條件」: MACD+KD 不需同 bar 交叉，
允許在 N 根 K 線窗口內先後出現 (提高訊號捕捉率)。

核心變化:
- 進場額外條件: RSI 在適當區間
- 交叉窗口: MACD 和 KD 交叉在 lookback_window 內先後出現即算數
- 更寬鬆的 KD 出場: K>80 或 K<20 直接出場
"""

from __future__ import annotations

from datetime import timedelta as _td
from decimal import Decimal

from txf.core.types import Bar
from txf.strategy.base import Strategy
from txf.strategy.indicators import macd, kd, ema, rsi


class MACDKDRSIFilter(Strategy):
    """MACD+KD 共振 + RSI 動能過濾."""

    def __init__(
        self,
        macd_fast: int = 12,
        macd_slow: int = 26,
        macd_signal: int = 9,
        kd_k_period: int = 9,
        kd_d_period: int = 3,
        trend_ema_period: int = 60,
        rsi_period: int = 14,
        rsi_buy_range: tuple[float, float] = (40, 65),
        rsi_sell_range: tuple[float, float] = (35, 60),
        lookback_window: int = 3,
        stop_loss_points: int = 30,
        take_profit_points: int = 55,
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
        self._rsi_period = rsi_period
        self._rsi_buy_lo, self._rsi_buy_hi = rsi_buy_range
        self._rsi_sell_lo, self._rsi_sell_hi = rsi_sell_range
        self._lookback = lookback_window
        self._sl = stop_loss_points
        self._tp = take_profit_points
        self._avoid_open = avoid_open_minutes
        self._avoid_close = avoid_close_minutes
        self._quantity = quantity

        self._entry_price: Decimal | None = None

    def on_bar(self, bar: Bar) -> None:
        warmup = max(self._macd_slow + self._macd_signal, self._trend_period, self._rsi_period) + 10
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
        rsi_val = rsi(close, self._rsi_period)

        trend_now = float(trend_line.iloc[-1])
        price_now = bar.close
        rsi_now = float(rsi_val.iloc[-1])
        k_now = float(k_val.iloc[-1])

        is_uptrend = float(price_now) > trend_now
        is_downtrend = float(price_now) < trend_now

        # Lookback window for signals (allow non-simultaneous crosses)
        def had_macd_bull(window: int) -> bool:
            for i in range(1, window + 1):
                if float(histogram.iloc[-i - 1]) <= 0 and float(histogram.iloc[-i]) > 0:
                    return True
            return False

        def had_macd_bear(window: int) -> bool:
            for i in range(1, window + 1):
                if float(histogram.iloc[-i - 1]) >= 0 and float(histogram.iloc[-i]) < 0:
                    return True
            return False

        def had_kd_golden(window: int) -> bool:
            for i in range(1, window + 1):
                if float(k_val.iloc[-i - 1]) <= float(d_val.iloc[-i - 1]) and \
                   float(k_val.iloc[-i]) > float(d_val.iloc[-i]):
                    return True
            return False

        def had_kd_death(window: int) -> bool:
            for i in range(1, window + 1):
                if float(k_val.iloc[-i - 1]) >= float(d_val.iloc[-i - 1]) and \
                   float(k_val.iloc[-i]) < float(d_val.iloc[-i]):
                    return True
            return False

        # -- Exit --
        if self.ctx.is_long and self._entry_price is not None:
            pnl = price_now - self._entry_price
            if pnl <= -self._sl or pnl >= self._tp:
                self.ctx.close_position()
                self._entry_price = None
                return
            if k_now > 80:  # KD overbought exit
                self.ctx.close_position()
                self._entry_price = None
                return

        elif self.ctx.is_short and self._entry_price is not None:
            pnl = self._entry_price - price_now
            if pnl <= -self._sl or pnl >= self._tp:
                self.ctx.close_position()
                self._entry_price = None
                return
            if k_now < 20:  # KD oversold exit
                self.ctx.close_position()
                self._entry_price = None
                return

        # -- Entry --
        if not self.ctx.is_flat or not in_window:
            return

        # RSI filter
        rsi_buy_ok = self._rsi_buy_lo <= rsi_now <= self._rsi_buy_hi
        rsi_sell_ok = self._rsi_sell_lo <= rsi_now <= self._rsi_sell_hi

        # BUY: uptrend + MACD bull + KD golden (within lookback window) + RSI in range
        if is_uptrend and rsi_buy_ok:
            if had_macd_bull(self._lookback) and had_kd_golden(self._lookback):
                self.ctx.buy(self._quantity)
                self._entry_price = price_now

        # SELL: downtrend + MACD bear + KD death (within lookback window) + RSI in range
        elif is_downtrend and rsi_sell_ok:
            if had_macd_bear(self._lookback) and had_kd_death(self._lookback):
                self.ctx.sell(self._quantity)
                self._entry_price = price_now
