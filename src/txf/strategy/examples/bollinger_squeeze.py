"""Bollinger Band Squeeze Breakout Strategy.

針對雙均線策略的缺陷設計：
1. 等待盤整後的爆發 — Bollinger Band 收窄代表波動壓縮，
   突破代表新趨勢啟動，避免在震盪中被來回打臉
2. 成交量確認 — 突破需搭配放量，過濾假突破
3. 動態停損 — 以 Bollinger 中軌 (SMA) 為移動停損線
4. 每日最多交易次數限制 — 防止過度交易

Logic:
- Squeeze detection: band_width < threshold (bands 收窄)
- BUY: 價格突破上軌 + 放量 + 在 squeeze 後
- SELL: 價格跌破下軌 + 放量 + 在 squeeze 後
- EXIT: 價格回穿中軌 (trailing stop on middle band)
"""

from __future__ import annotations

from txf.core.types import Bar
from txf.strategy.base import Strategy
from txf.strategy.indicators import bollinger_bands, sma


class BollingerSqueezeBreakout(Strategy):
    """布林通道壓縮突破策略.

    Parameters:
        bb_period: 布林通道週期 (default: 20)
        bb_std: 標準差倍數 (default: 2.0)
        squeeze_lookback: 判斷 squeeze 的回顧期 (default: 50)
        squeeze_percentile: band width 低於此百分位視為 squeeze (default: 25)
        volume_multiple: 成交量需為均量的倍數 (default: 1.3)
        volume_period: 均量計算週期 (default: 20)
        max_trades_per_day: 每日最多交易次數 (default: 3)
        quantity: 每次交易口數 (default: 1)
    """

    def __init__(
        self,
        bb_period: int = 20,
        bb_std: float = 2.0,
        squeeze_lookback: int = 50,
        squeeze_percentile: float = 25,
        volume_multiple: float = 1.3,
        volume_period: int = 20,
        max_trades_per_day: int = 3,
        quantity: int = 1,
    ) -> None:
        super().__init__(
            bb_period=bb_period, bb_std=bb_std,
            squeeze_lookback=squeeze_lookback, squeeze_percentile=squeeze_percentile,
            volume_multiple=volume_multiple, volume_period=volume_period,
            max_trades_per_day=max_trades_per_day, quantity=quantity,
        )
        self._bb_period = bb_period
        self._bb_std = bb_std
        self._squeeze_lookback = squeeze_lookback
        self._squeeze_pct = squeeze_percentile
        self._vol_multiple = volume_multiple
        self._vol_period = volume_period
        self._max_daily_trades = max_trades_per_day
        self._quantity = quantity

        self._current_date = None
        self._daily_trade_count = 0
        self._was_squeezed = False

    def on_bar(self, bar: Bar) -> None:
        warmup = max(self._bb_period, self._squeeze_lookback, self._vol_period) + 5
        if self.ctx.bar_count < warmup:
            return

        # Reset daily trade counter
        bar_date = bar.datetime.date()
        if bar_date != self._current_date:
            self._current_date = bar_date
            self._daily_trade_count = 0

        close = self.ctx.close
        volume = self.ctx.volume

        # Compute indicators
        upper, middle, lower = bollinger_bands(close, self._bb_period, self._bb_std)
        band_width = (upper - lower) / middle  # normalized width

        # Squeeze detection: current band_width in the bottom percentile
        recent_bw = band_width.dropna().iloc[-self._squeeze_lookback:]
        if len(recent_bw) < self._squeeze_lookback:
            return

        bw_threshold = recent_bw.quantile(self._squeeze_pct / 100)
        is_squeezed = band_width.iloc[-1] <= bw_threshold

        # Track squeeze state
        if is_squeezed:
            self._was_squeezed = True

        # Volume confirmation
        avg_volume = sma(volume.astype(float), self._vol_period).iloc[-1]
        current_volume = float(volume.iloc[-1])
        volume_surge = current_volume > avg_volume * self._vol_multiple

        current_close = float(close.iloc[-1])
        current_upper = float(upper.iloc[-1])
        current_lower = float(lower.iloc[-1])
        current_middle = float(middle.iloc[-1])

        # -- Exit logic: price crosses back through middle band --
        if self.ctx.is_long:
            if current_close < current_middle:
                self.ctx.close_position()
                self._was_squeezed = False
                return

        elif self.ctx.is_short:
            if current_close > current_middle:
                self.ctx.close_position()
                self._was_squeezed = False
                return

        # -- Entry logic --
        if not self.ctx.is_flat:
            return
        if self._daily_trade_count >= self._max_daily_trades:
            return
        if not self._was_squeezed:
            return

        # Breakout above upper band + volume
        if current_close > current_upper and volume_surge:
            self.ctx.buy(self._quantity)
            self._daily_trade_count += 1
            self._was_squeezed = False

        # Breakdown below lower band + volume
        elif current_close < current_lower and volume_surge:
            self.ctx.sell(self._quantity)
            self._daily_trade_count += 1
            self._was_squeezed = False
