"""MACD + KD Confluence Strategy (多指標共振策略).

針對雙均線策略的缺陷設計：
1. 多指標確認 — MACD (趨勢) + KD (動能) 同時發出訊號才進場，
   大幅降低假訊號，提高勝率
2. 趨勢過濾 — 用長期 EMA 判斷大方向，只做順勢單
3. 固定點數停損/停利 — 明確的風險報酬比 (R:R >= 1.5)
4. 交易時段過濾 — 避開開盤前 15 分鐘和收盤前 15 分鐘的劇烈波動

Logic:
- 趨勢判斷: 價格 > EMA(60) → 只做多, 價格 < EMA(60) → 只做空
- BUY: MACD histogram 翻正 + K線上穿D線 (KD 黃金交叉) + 順勢
- SELL: MACD histogram 翻負 + K線下穿D線 (KD 死亡交叉) + 順勢
- EXIT: 固定停利/停損 or KD 反向交叉
"""

from __future__ import annotations

from datetime import time
from decimal import Decimal

from txf.core.types import Bar
from txf.strategy.base import Strategy
from txf.strategy.indicators import macd, kd, ema


class MACDKDConfluence(Strategy):
    """MACD + KD 多指標共振策略.

    Parameters:
        macd_fast: MACD 快線週期 (default: 12)
        macd_slow: MACD 慢線週期 (default: 26)
        macd_signal: MACD 信號線週期 (default: 9)
        kd_k_period: KD K值週期 (default: 9)
        kd_d_period: KD D值平滑 (default: 3)
        trend_ema_period: 趨勢過濾 EMA 週期 (default: 60)
        stop_loss_points: 停損點數 (default: 30)
        take_profit_points: 停利點數 (default: 50)
        avoid_open_minutes: 避開開盤前N分鐘 (default: 15)
        avoid_close_minutes: 避開收盤前N分鐘 (default: 15)
        quantity: 每次交易口數 (default: 1)
    """

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
        avoid_open_minutes: int = 15,
        avoid_close_minutes: int = 15,
        quantity: int = 1,
    ) -> None:
        super().__init__(
            macd_fast=macd_fast, macd_slow=macd_slow, macd_signal=macd_signal,
            kd_k_period=kd_k_period, kd_d_period=kd_d_period,
            trend_ema_period=trend_ema_period,
            stop_loss_points=stop_loss_points, take_profit_points=take_profit_points,
            avoid_open_minutes=avoid_open_minutes, avoid_close_minutes=avoid_close_minutes,
            quantity=quantity,
        )
        self._macd_fast = macd_fast
        self._macd_slow = macd_slow
        self._macd_signal = macd_signal
        self._kd_k = kd_k_period
        self._kd_d = kd_d_period
        self._trend_period = trend_ema_period
        self._sl_points = stop_loss_points
        self._tp_points = take_profit_points
        self._avoid_open = avoid_open_minutes
        self._avoid_close = avoid_close_minutes
        self._quantity = quantity

        self._entry_price: Decimal | None = None

    def on_bar(self, bar: Bar) -> None:
        warmup = max(self._macd_slow + self._macd_signal, self._trend_period, self._kd_k) + 5
        if self.ctx.bar_count < warmup:
            return

        # Time filter: avoid volatile open/close periods
        bar_time = bar.datetime.time()
        from datetime import timedelta as _td
        _open_dt = bar.datetime.replace(hour=8, minute=45, second=0)
        _close_dt = bar.datetime.replace(hour=13, minute=45, second=0)
        avoid_start = (_open_dt + _td(minutes=self._avoid_open)).time()
        avoid_end = (_close_dt - _td(minutes=self._avoid_close)).time()

        in_trading_window = avoid_start <= bar_time <= avoid_end

        close = self.ctx.close
        high = self.ctx.high
        low = self.ctx.low

        # Compute indicators
        macd_line, signal_line, histogram = macd(
            close, self._macd_fast, self._macd_slow, self._macd_signal
        )
        k_val, d_val = kd(high, low, close, self._kd_k, self._kd_d)
        trend_line = ema(close, self._trend_period)

        # Current and previous values
        hist_now = float(histogram.iloc[-1])
        hist_prev = float(histogram.iloc[-2])
        k_now = float(k_val.iloc[-1])
        k_prev = float(k_val.iloc[-2])
        d_now = float(d_val.iloc[-1])
        d_prev = float(d_val.iloc[-2])
        trend_now = float(trend_line.iloc[-1])
        price_now = float(close.iloc[-1])

        # Trend direction
        is_uptrend = price_now > trend_now
        is_downtrend = price_now < trend_now

        # Signal detection
        macd_bull = hist_prev <= 0 and hist_now > 0  # histogram flips positive
        macd_bear = hist_prev >= 0 and hist_now < 0  # histogram flips negative
        kd_golden = k_prev <= d_prev and k_now > d_now  # K crosses above D
        kd_death = k_prev >= d_prev and k_now < d_now   # K crosses below D

        current_price = bar.close

        # -- Exit logic: fixed stop loss / take profit --
        if self.ctx.is_long and self._entry_price is not None:
            pnl_points = current_price - self._entry_price
            if pnl_points <= -self._sl_points or pnl_points >= self._tp_points:
                self.ctx.close_position()
                self._entry_price = None
                return
            # Also exit on KD death cross (momentum reversal)
            if kd_death and k_now > 70:
                self.ctx.close_position()
                self._entry_price = None
                return

        elif self.ctx.is_short and self._entry_price is not None:
            pnl_points = self._entry_price - current_price
            if pnl_points <= -self._sl_points or pnl_points >= self._tp_points:
                self.ctx.close_position()
                self._entry_price = None
                return
            # Also exit on KD golden cross (momentum reversal)
            if kd_golden and k_now < 30:
                self.ctx.close_position()
                self._entry_price = None
                return

        # -- Entry logic: confluence required --
        if not self.ctx.is_flat:
            return
        if not in_trading_window:
            return

        # BUY: uptrend + MACD bullish + KD golden cross
        if is_uptrend and macd_bull and kd_golden:
            self.ctx.buy(self._quantity)
            self._entry_price = current_price

        # SELL: downtrend + MACD bearish + KD death cross
        elif is_downtrend and macd_bear and kd_death:
            self.ctx.sell(self._quantity)
            self._entry_price = current_price
