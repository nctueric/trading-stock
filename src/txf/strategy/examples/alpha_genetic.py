"""Parametric Alpha Strategy for Genetic Algorithm.

This strategy is controlled by a gene dictionary that determines:
- Which signal type to use (MACD, KD, Supertrend, WaveTrend, Bollinger)
- Indicator parameters (periods, thresholds)
- Exit logic (SL/TP multipliers, trailing stop)
- Filters (ADX, RSI, time window)
"""

from __future__ import annotations

import math
from datetime import timedelta as _td
from decimal import Decimal

from txf.core.types import Bar
from txf.strategy.base import Strategy
from txf.strategy.indicators import (
    macd, kd, ema, atr, rsi, bollinger_bands, supertrend, wavetrend, adx,
)

# Signal type constants
SIG_MACD = 0
SIG_KD = 1
SIG_SUPERTREND = 2
SIG_WAVETREND = 3
SIG_BOLLINGER = 4


class AlphaGenetic(Strategy):
    """Parametric strategy controlled by a gene dictionary."""

    def __init__(self, genes: dict | None = None, **kwargs) -> None:
        super().__init__()
        g = genes or kwargs
        self._signal = int(g.get("signal_type", 0))
        self._trend_period = int(g.get("trend_period", 60))
        self._fast = int(g.get("fast_period", 12))
        self._slow = int(g.get("slow_period", 26))
        self._sig_period = int(g.get("signal_period", 9))
        self._osc_period = int(g.get("osc_period", 14))
        self._sl_mult = float(g.get("sl_mult", 2.0))
        self._tp_mult = float(g.get("tp_mult", 3.5))
        self._use_trailing = bool(g.get("use_trailing", False))
        self._trail_mult = float(g.get("trail_mult", 1.5))
        self._trail_trigger = float(g.get("trail_trigger", 1.0))
        self._avoid_open = int(g.get("avoid_open", 15))
        self._avoid_close = int(g.get("avoid_close", 15))
        self._use_adx = bool(g.get("use_adx_filter", False))
        self._adx_min = float(g.get("adx_min", 25))
        self._use_rsi = bool(g.get("use_rsi_filter", False))
        self._rsi_ob = float(g.get("rsi_ob", 70))
        self._rsi_os = float(g.get("rsi_os", 30))
        self._atr_period = int(g.get("atr_period", 14))

    def on_init(self) -> None:
        self._entry_price: Decimal | None = None
        self._sl: float = 30.0
        self._tp: float = 50.0
        self._trailing: float | None = None
        self._best_pnl: float = 0.0

    def _reset(self):
        self._entry_price = None
        self._trailing = None
        self._best_pnl = 0.0

    def on_bar(self, bar: Bar) -> None:
        warmup = max(self._slow + self._sig_period, self._trend_period,
                     self._osc_period, self._atr_period, 28) + 10
        if self.ctx.bar_count < warmup:
            return

        bt = bar.datetime.time()
        t_open = (bar.datetime.replace(hour=8, minute=45, second=0) + _td(minutes=self._avoid_open)).time()
        t_close = (bar.datetime.replace(hour=13, minute=45, second=0) - _td(minutes=self._avoid_close)).time()
        in_window = t_open <= bt <= t_close

        c = self.ctx.close
        h = self.ctx.high
        lo = self.ctx.low
        price_now = bar.close
        pf = float(price_now)

        def sf(s, idx=-1):
            v = float(s.iloc[idx])
            return v if not math.isnan(v) else 0.0

        trend_v = ema(c, self._trend_period)
        atr_v = atr(h, lo, c, self._atr_period)
        tn = sf(trend_v)
        an = sf(atr_v) or 30.0
        is_up = pf > tn
        is_down = pf < tn

        # Optional filters
        adx_ok = True
        if self._use_adx:
            adx_v, pdi, mdi = adx(h, lo, c, self._atr_period)
            ax = sf(adx_v)
            adx_ok = ax >= self._adx_min

        rsi_buy_ok = True
        rsi_sell_ok = True
        if self._use_rsi:
            rsi_v = rsi(c, self._osc_period)
            rn = sf(rsi_v)
            rsi_buy_ok = rn < self._rsi_ob
            rsi_sell_ok = rn > self._rsi_os

        # Generate signal based on signal_type
        buy_sig, sell_sig = False, False

        if self._signal == SIG_MACD:
            ml, sl_m, hist = macd(c, self._fast, self._slow, self._sig_period)
            hn, hp = sf(hist), sf(hist, -2)
            buy_sig = hp <= 0 and hn > 0 and is_up
            sell_sig = hp >= 0 and hn < 0 and is_down

        elif self._signal == SIG_KD:
            k_v, d_v = kd(h, lo, c, self._osc_period, 3)
            kn, kp = sf(k_v), sf(k_v, -2)
            dn, dp = sf(d_v), sf(d_v, -2)
            buy_sig = kp <= dp and kn > dn and kn < 80 and is_up
            sell_sig = kp >= dp and kn < dn and kn > 20 and is_down

        elif self._signal == SIG_SUPERTREND:
            st_l, st_d = supertrend(h, lo, c, self._osc_period, 3.0)
            dn_now = int(st_d.iloc[-1])
            dn_prev = int(st_d.iloc[-2])
            buy_sig = dn_prev <= 0 and dn_now == 1
            sell_sig = dn_prev >= 0 and dn_now == -1

        elif self._signal == SIG_WAVETREND:
            wt1, wt2 = wavetrend(h, lo, c, self._osc_period, self._slow)
            w1n, w2n = sf(wt1), sf(wt2)
            w1p, w2p = sf(wt1, -2), sf(wt2, -2)
            buy_sig = w1p <= w2p and w1n > w2n and w1p < 0 and is_up
            sell_sig = w1p >= w2p and w1n < w2n and w1p > 0 and is_down

        elif self._signal == SIG_BOLLINGER:
            bb_up, bb_mid, bb_lo = bollinger_bands(c, self._slow, 2.0)
            upper, lower = sf(bb_up), sf(bb_lo)
            prev_c = sf(c, -2)
            buy_sig = prev_c <= lower and pf > lower and is_up
            sell_sig = prev_c >= upper and pf < upper and is_down

        # ── Exit ──
        if self.ctx.is_long and self._entry_price is not None:
            pnl = float(price_now - self._entry_price)
            if self._use_trailing:
                if pnl > self._best_pnl:
                    self._best_pnl = pnl
                if self._best_pnl > an * self._trail_trigger:
                    new_t = pf - an * self._trail_mult
                    if self._trailing is None or new_t > self._trailing:
                        self._trailing = new_t
                if self._trailing is not None and pf <= self._trailing:
                    self.ctx.close_position(); self._reset(); return
            if pnl <= -self._sl or pnl >= self._tp:
                self.ctx.close_position(); self._reset(); return
            if sell_sig and pnl > 0:
                self.ctx.close_position(); self._reset(); return

        elif self.ctx.is_short and self._entry_price is not None:
            pnl = float(self._entry_price - price_now)
            if self._use_trailing:
                if pnl > self._best_pnl:
                    self._best_pnl = pnl
                if self._best_pnl > an * self._trail_trigger:
                    new_t = pf + an * self._trail_mult
                    if self._trailing is None or new_t < self._trailing:
                        self._trailing = new_t
                if self._trailing is not None and pf >= self._trailing:
                    self.ctx.close_position(); self._reset(); return
            if pnl <= -self._sl or pnl >= self._tp:
                self.ctx.close_position(); self._reset(); return
            if buy_sig and pnl > 0:
                self.ctx.close_position(); self._reset(); return

        # ── Entry ──
        if not self.ctx.is_flat or not in_window:
            return

        self._sl = max(15.0, an * self._sl_mult)
        self._tp = max(20.0, an * self._tp_mult)

        if buy_sig and adx_ok and rsi_buy_ok:
            self.ctx.buy(1)
            self._entry_price = price_now
            self._best_pnl = 0.0
            self._trailing = None
        elif sell_sig and adx_ok and rsi_sell_ok:
            self.ctx.sell(1)
            self._entry_price = price_now
            self._best_pnl = 0.0
            self._trailing = None
