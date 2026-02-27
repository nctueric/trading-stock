"""Strategy H: VWAP + Squeeze + RSI 多重確認策略.

VWAP 機構偏差 + Squeeze 能量 + RSI 動能三重確認.
"""

from __future__ import annotations

import math
from datetime import timedelta as _td
from decimal import Decimal

import pandas as pd

from txf.core.types import Bar
from txf.strategy.base import Strategy
from txf.strategy.indicators import squeeze_momentum, rsi, atr, vwap, ema


class VWAPSqueezeRSI(Strategy):
    """VWAP 偏差 + Squeeze 能量 + RSI 確認."""

    def on_init(self) -> None:
        self._entry_price: Decimal | None = None
        self._sl: float = 30.0
        self._tp: float = 50.0

    def on_bar(self, bar: Bar) -> None:
        if self.ctx.bar_count < 80:
            return

        bt = bar.datetime.time()
        t_open = (bar.datetime.replace(hour=8, minute=45, second=0) + _td(minutes=20)).time()
        t_close = (bar.datetime.replace(hour=13, minute=45, second=0) - _td(minutes=15)).time()
        in_window = t_open <= bt <= t_close

        c, h, lo, vol = self.ctx.close, self.ctx.high, self.ctx.low, self.ctx.volume
        bars = self.ctx.bars
        dt_series = pd.Series([b.datetime for b in bars])

        sq_on, mom = squeeze_momentum(h, lo, c)
        rsi_v = rsi(c, 14)
        atr_v = atr(h, lo, c, 14)
        vwap_v = vwap(h, lo, c, vol, dt_series)
        trend = ema(c, 60)

        pf = float(bar.close)

        def sf(s, idx=-1):
            v = float(s.iloc[idx])
            return v if not math.isnan(v) else 0.0

        rn = sf(rsi_v)
        an = sf(atr_v) or 30.0
        vn = sf(vwap_v)
        mn, mp = sf(mom), sf(mom, -2)
        sq_now = bool(sq_on.iloc[-1]) if len(sq_on) > 0 else False
        sq_prev = bool(sq_on.iloc[-2]) if len(sq_on) > 1 else False
        tn = sf(trend)

        released = sq_prev and not sq_now
        above_vwap = pf > vn
        below_vwap = pf < vn

        # Exit
        if self.ctx.is_long and self._entry_price is not None:
            pnl = float(bar.close - self._entry_price)
            if pnl <= -self._sl or pnl >= self._tp:
                self.ctx.close_position(); self._entry_price = None; return
            if below_vwap and pnl > 0:
                self.ctx.close_position(); self._entry_price = None; return
            if rn > 75:
                self.ctx.close_position(); self._entry_price = None; return
        elif self.ctx.is_short and self._entry_price is not None:
            pnl = float(self._entry_price - bar.close)
            if pnl <= -self._sl or pnl >= self._tp:
                self.ctx.close_position(); self._entry_price = None; return
            if above_vwap and pnl > 0:
                self.ctx.close_position(); self._entry_price = None; return
            if rn < 25:
                self.ctx.close_position(); self._entry_price = None; return

        if not self.ctx.is_flat or not in_window:
            return

        self._sl = max(20.0, an * 2.0)
        self._tp = max(30.0, an * 3.0)

        # Buy: above VWAP + squeeze signal + RSI 40-65
        if above_vwap and 40 <= rn <= 65 and pf > tn:
            if (released and mn > 0) or (mn > 0 and mn > mp and abs(mn) > an * 0.3):
                self.ctx.buy(1); self._entry_price = bar.close; return

        # Sell: below VWAP + squeeze signal + RSI 35-60
        if below_vwap and 35 <= rn <= 60 and pf < tn:
            if (released and mn < 0) or (mn < 0 and mn < mp and abs(mn) > an * 0.3):
                self.ctx.sell(1); self._entry_price = bar.close
