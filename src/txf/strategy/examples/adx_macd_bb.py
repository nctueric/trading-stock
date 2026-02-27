"""Strategy J: ADX + MACD + Bollinger Bands 三重交叉策略.

ADX 作為交易開關 + MACD 動量方向 + BB 位置評估.
"""

from __future__ import annotations

import math
from datetime import timedelta as _td
from decimal import Decimal

from txf.core.types import Bar
from txf.strategy.base import Strategy
from txf.strategy.indicators import adx, macd, bollinger_bands, atr, ema


class ADXMACDBollinger(Strategy):
    """ADX 趨勢開關 + MACD 動量 + BB 價格位置."""

    def on_init(self) -> None:
        self._entry_price: Decimal | None = None

    def on_bar(self, bar: Bar) -> None:
        if self.ctx.bar_count < 80:
            return

        bt = bar.datetime.time()
        t_open = (bar.datetime.replace(hour=8, minute=45, second=0) + _td(minutes=15)).time()
        t_close = (bar.datetime.replace(hour=13, minute=45, second=0) - _td(minutes=15)).time()
        in_window = t_open <= bt <= t_close

        c, h, lo = self.ctx.close, self.ctx.high, self.ctx.low

        adx_v, pdi, mdi = adx(h, lo, c, 14)
        macd_l, sig_l, hist = macd(c, 12, 26, 9)
        bb_up, bb_mid, bb_lo = bollinger_bands(c, 20, 2.0)
        trend = ema(c, 60)

        pf = float(bar.close)

        def sf(s, idx=-1):
            v = float(s.iloc[idx])
            return v if not math.isnan(v) else 0.0

        ax = sf(adx_v)
        pn, mn_di = sf(pdi), sf(mdi)
        hn, hp = sf(hist), sf(hist, -2)
        upper, middle, lower = sf(bb_up), sf(bb_mid), sf(bb_lo)
        tn = sf(trend)

        macd_bull = hp <= 0 and hn > 0
        macd_bear = hp >= 0 and hn < 0

        bw = upper - lower if upper > lower else 1.0
        bb_pos = (pf - lower) / bw

        sl, tp = 35, 55

        # Exit
        if self.ctx.is_long and self._entry_price is not None:
            pnl = bar.close - self._entry_price
            if pnl <= -sl or pnl >= tp:
                self.ctx.close_position(); self._entry_price = None; return
            if pf >= upper and float(pnl) > 0:
                self.ctx.close_position(); self._entry_price = None; return
            if hn < 0 and hp >= 0 and float(pnl) > 0:
                self.ctx.close_position(); self._entry_price = None; return
            if ax < 18:
                self.ctx.close_position(); self._entry_price = None; return

        elif self.ctx.is_short and self._entry_price is not None:
            pnl = self._entry_price - bar.close
            if pnl <= -sl or pnl >= tp:
                self.ctx.close_position(); self._entry_price = None; return
            if pf <= lower and float(pnl) > 0:
                self.ctx.close_position(); self._entry_price = None; return
            if hn > 0 and hp <= 0 and float(pnl) > 0:
                self.ctx.close_position(); self._entry_price = None; return
            if ax < 18:
                self.ctx.close_position(); self._entry_price = None; return

        if not self.ctx.is_flat or not in_window:
            return

        if ax >= 25 and pn > mn_di and macd_bull and 0.3 <= bb_pos <= 0.8 and pf > tn:
            self.ctx.buy(1); self._entry_price = bar.close
        elif ax >= 25 and mn_di > pn and macd_bear and 0.2 <= bb_pos <= 0.7 and pf < tn:
            self.ctx.sell(1); self._entry_price = bar.close
