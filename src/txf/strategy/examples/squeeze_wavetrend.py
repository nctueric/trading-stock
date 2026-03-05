"""Strategy F: Squeeze Momentum + WaveTrend 壓縮突破策略.

Squeeze 偵測能量壓縮→釋放, WaveTrend 提供精準進場時機.
"""

from __future__ import annotations

import math
from datetime import timedelta as _td
from decimal import Decimal

from txf.core.types import Bar
from txf.strategy.base import Strategy
from txf.strategy.indicators import squeeze_momentum, wavetrend, atr, ema


class SqueezeWaveTrend(Strategy):
    """Squeeze 壓縮突破 + WaveTrend 精準進場."""

    def on_init(self) -> None:
        self._entry_price: Decimal | None = None
        self._sl: float = 30.0
        self._tp: float = 50.0

    def on_bar(self, bar: Bar) -> None:
        if self.ctx.bar_count < 80:
            return

        bt = bar.datetime.time()
        t_open = (bar.datetime.replace(hour=8, minute=45, second=0) + _td(minutes=15)).time()
        t_close = (bar.datetime.replace(hour=13, minute=45, second=0) - _td(minutes=15)).time()
        in_window = t_open <= bt <= t_close

        c, h, lo = self.ctx.close, self.ctx.high, self.ctx.low

        sq_on, mom = squeeze_momentum(h, lo, c)
        wt1, wt2 = wavetrend(h, lo, c)
        atr_v = atr(h, lo, c, 14)
        trend = ema(c, 60)

        pf = float(bar.close)

        def sf(s, idx=-1):
            v = float(s.iloc[idx])
            return v if not math.isnan(v) else 0.0

        wt1n, wt2n = sf(wt1), sf(wt2)
        wt1p, wt2p = sf(wt1, -2), sf(wt2, -2)
        mn, mp = sf(mom), sf(mom, -2)
        an = sf(atr_v) or 30.0
        tn = sf(trend)
        sq_now = bool(sq_on.iloc[-1]) if len(sq_on) > 0 else False
        sq_prev = bool(sq_on.iloc[-2]) if len(sq_on) > 1 else False

        released = sq_prev and not sq_now
        wt_bull = wt1p <= wt2p and wt1n > wt2n
        wt_bear = wt1p >= wt2p and wt1n < wt2n

        # Exit
        if self.ctx.is_long and self._entry_price is not None:
            pnl = float(bar.close - self._entry_price)
            if pnl <= -self._sl or pnl >= self._tp:
                self.ctx.close_position(); self._entry_price = None; return
            if wt1n > 53 and wt1n < wt1p:
                self.ctx.close_position(); self._entry_price = None; return
            if mn < 0 and mp >= 0:
                self.ctx.close_position(); self._entry_price = None; return
        elif self.ctx.is_short and self._entry_price is not None:
            pnl = float(self._entry_price - bar.close)
            if pnl <= -self._sl or pnl >= self._tp:
                self.ctx.close_position(); self._entry_price = None; return
            if wt1n < -53 and wt1n > wt1p:
                self.ctx.close_position(); self._entry_price = None; return
            if mn > 0 and mp <= 0:
                self.ctx.close_position(); self._entry_price = None; return

        if not self.ctx.is_flat or not in_window:
            return

        self._sl = max(20.0, an * 2.0)
        self._tp = max(30.0, an * 3.0)

        if released and mn > 0 and mn > mp and wt1n > wt2n and wt1n < 53 and pf > tn:
            self.ctx.buy(1); self._entry_price = bar.close
        elif released and mn < 0 and mn < mp and wt1n < wt2n and wt1n > -53 and pf < tn:
            self.ctx.sell(1); self._entry_price = bar.close
        elif abs(mn) > an * 0.5:
            if wt_bull and mn > 0 and pf > tn and wt1n < 30:
                self.ctx.buy(1); self._entry_price = bar.close
            elif wt_bear and mn < 0 and pf < tn and wt1n > -30:
                self.ctx.sell(1); self._entry_price = bar.close
