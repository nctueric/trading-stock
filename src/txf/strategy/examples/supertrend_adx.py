"""Strategy G: Supertrend + ADX 趨勢強度過濾策略.

ADX 確認趨勢存在 → Supertrend 翻轉時進場.
"""

from __future__ import annotations

import math
from datetime import timedelta as _td
from decimal import Decimal

from txf.core.types import Bar
from txf.strategy.base import Strategy
from txf.strategy.indicators import supertrend, adx, atr, ema


class SupertrendADX(Strategy):
    """Supertrend 趨勢追蹤 + ADX 強度過濾."""

    def on_init(self) -> None:
        self._entry_price: Decimal | None = None
        self._sl: float = 30.0
        self._tp: float = 55.0

    def on_bar(self, bar: Bar) -> None:
        if self.ctx.bar_count < 80:
            return

        bt = bar.datetime.time()
        t_open = (bar.datetime.replace(hour=8, minute=45, second=0) + _td(minutes=15)).time()
        t_close = (bar.datetime.replace(hour=13, minute=45, second=0) - _td(minutes=15)).time()
        in_window = t_open <= bt <= t_close

        c, h, lo = self.ctx.close, self.ctx.high, self.ctx.low

        st_line, st_dir = supertrend(h, lo, c, 10, 3.0)
        adx_v, pdi, mdi = adx(h, lo, c, 14)
        atr_v = atr(h, lo, c, 14)
        trend = ema(c, 60)

        def sf(s, idx=-1):
            v = float(s.iloc[idx])
            return v if not math.isnan(v) else 0.0

        dn = int(st_dir.iloc[-1])
        dp = int(st_dir.iloc[-2])
        ax = sf(adx_v)
        pn, mn_di = sf(pdi), sf(mdi)
        an = sf(atr_v) or 30.0

        flip_bull = dp <= 0 and dn == 1
        flip_bear = dp >= 0 and dn == -1

        # Exit
        if self.ctx.is_long and self._entry_price is not None:
            pnl = float(bar.close - self._entry_price)
            if pnl <= -self._sl or pnl >= self._tp:
                self.ctx.close_position(); self._entry_price = None; return
            if dn == -1:
                self.ctx.close_position(); self._entry_price = None; return
            if ax < 18 and pnl > 0:
                self.ctx.close_position(); self._entry_price = None; return
        elif self.ctx.is_short and self._entry_price is not None:
            pnl = float(self._entry_price - bar.close)
            if pnl <= -self._sl or pnl >= self._tp:
                self.ctx.close_position(); self._entry_price = None; return
            if dn == 1:
                self.ctx.close_position(); self._entry_price = None; return
            if ax < 18 and pnl > 0:
                self.ctx.close_position(); self._entry_price = None; return

        if not self.ctx.is_flat or not in_window:
            return

        self._sl = max(20.0, an * 2.0)
        self._tp = max(35.0, an * 3.5)

        if flip_bull and ax >= 25 and pn > mn_di:
            self.ctx.buy(1); self._entry_price = bar.close
        elif flip_bear and ax >= 25 and mn_di > pn:
            self.ctx.sell(1); self._entry_price = bar.close
