"""Strategy I: WaveTrend + Supertrend + ATR 動態出場策略.

Supertrend 過濾大方向 → WaveTrend 交叉精準進場 → ATR 追蹤出場.
"""

from __future__ import annotations

import math
from datetime import timedelta as _td
from decimal import Decimal

from txf.core.types import Bar
from txf.strategy.base import Strategy
from txf.strategy.indicators import wavetrend, supertrend, atr, ema


class WaveTrendSupertrend(Strategy):
    """WaveTrend 擺盪進場 + Supertrend 趨勢過濾 + ATR 追蹤出場."""

    def on_init(self) -> None:
        self._entry_price: Decimal | None = None
        self._sl: float = 30.0
        self._tp: float = 60.0
        self._trailing: float | None = None
        self._best_pnl: float = 0.0

    def _reset(self):
        self._entry_price = None
        self._trailing = None
        self._best_pnl = 0.0

    def on_bar(self, bar: Bar) -> None:
        if self.ctx.bar_count < 80:
            return

        bt = bar.datetime.time()
        t_open = (bar.datetime.replace(hour=8, minute=45, second=0) + _td(minutes=15)).time()
        t_close = (bar.datetime.replace(hour=13, minute=45, second=0) - _td(minutes=15)).time()
        in_window = t_open <= bt <= t_close

        c, h, lo = self.ctx.close, self.ctx.high, self.ctx.low

        wt1, wt2 = wavetrend(h, lo, c)
        st_line, st_dir = supertrend(h, lo, c, 10, 3.0)
        atr_v = atr(h, lo, c, 14)
        trend = ema(c, 60)

        def sf(s, idx=-1):
            v = float(s.iloc[idx])
            return v if not math.isnan(v) else 0.0

        wt1n, wt2n = sf(wt1), sf(wt2)
        wt1p, wt2p = sf(wt1, -2), sf(wt2, -2)
        dn = int(st_dir.iloc[-1])
        an = sf(atr_v) or 30.0
        tn = sf(trend)
        pf = float(bar.close)

        wt_bull = wt1p <= wt2p and wt1n > wt2n
        wt_bear = wt1p >= wt2p and wt1n < wt2n

        # Exit
        if self.ctx.is_long and self._entry_price is not None:
            pnl = float(bar.close - self._entry_price)
            if pnl > self._best_pnl:
                self._best_pnl = pnl
            if self._best_pnl > an * 1.0:
                new_t = pf - an * 1.5
                if self._trailing is None or new_t > self._trailing:
                    self._trailing = new_t
            if pnl <= -self._sl:
                self.ctx.close_position(); self._reset(); return
            if pnl >= self._tp:
                self.ctx.close_position(); self._reset(); return
            if self._trailing is not None and pf <= self._trailing:
                self.ctx.close_position(); self._reset(); return
            if dn == -1:
                self.ctx.close_position(); self._reset(); return
            if wt1n > 53 and wt_bear:
                self.ctx.close_position(); self._reset(); return

        elif self.ctx.is_short and self._entry_price is not None:
            pnl = float(self._entry_price - bar.close)
            if pnl > self._best_pnl:
                self._best_pnl = pnl
            if self._best_pnl > an * 1.0:
                new_t = pf + an * 1.5
                if self._trailing is None or new_t < self._trailing:
                    self._trailing = new_t
            if pnl <= -self._sl:
                self.ctx.close_position(); self._reset(); return
            if pnl >= self._tp:
                self.ctx.close_position(); self._reset(); return
            if self._trailing is not None and pf >= self._trailing:
                self.ctx.close_position(); self._reset(); return
            if dn == 1:
                self.ctx.close_position(); self._reset(); return
            if wt1n < -53 and wt_bull:
                self.ctx.close_position(); self._reset(); return

        if not self.ctx.is_flat or not in_window:
            return

        self._sl = max(20.0, an * 2.0)
        self._tp = max(40.0, an * 4.0)

        if dn == 1 and wt_bull and wt1p < 0 and pf > tn:
            self.ctx.buy(1); self._entry_price = bar.close; self._best_pnl = 0.0; self._trailing = None
        elif dn == -1 and wt_bear and wt1p > 0 and pf < tn:
            self.ctx.sell(1); self._entry_price = bar.close; self._best_pnl = 0.0; self._trailing = None
