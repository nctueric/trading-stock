"""Technical indicator library.

All functions operate on pandas Series or numpy arrays and return
the same type. Designed for use within Strategy.on_bar() via bar history.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def sma(series: pd.Series, period: int) -> pd.Series:
    """Simple Moving Average."""
    return series.rolling(window=period, min_periods=period).mean()


def ema(series: pd.Series, period: int) -> pd.Series:
    """Exponential Moving Average."""
    return series.ewm(span=period, adjust=False, min_periods=period).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Relative Strength Index."""
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    result = 100.0 - (100.0 / (1.0 + rs))
    # When avg_loss is 0 (all gains), RSI = 100
    result = result.fillna(100.0)
    # Restore NaN for warmup period
    result.iloc[: period] = np.nan
    return result


def kd(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    k_period: int = 9,
    d_period: int = 3,
) -> tuple[pd.Series, pd.Series]:
    """KD Stochastic Oscillator (commonly used in Taiwan markets)."""
    lowest = low.rolling(window=k_period, min_periods=k_period).min()
    highest = high.rolling(window=k_period, min_periods=k_period).max()
    rsv = (close - lowest) / (highest - lowest).replace(0, np.nan) * 100
    k = rsv.ewm(alpha=1.0 / d_period, adjust=False, min_periods=1).mean()
    d = k.ewm(alpha=1.0 / d_period, adjust=False, min_periods=1).mean()
    return k, d


def macd(
    series: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """MACD (Moving Average Convergence Divergence).

    Returns: (macd_line, signal_line, histogram)
    """
    ema_fast = ema(series, fast)
    ema_slow = ema(series, slow)
    macd_line = ema_fast - ema_slow
    signal_line = ema(macd_line, signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def atr(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 14,
) -> pd.Series:
    """Average True Range."""
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.rolling(window=period, min_periods=period).mean()


def bollinger_bands(
    series: pd.Series,
    period: int = 20,
    num_std: float = 2.0,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Bollinger Bands.

    Returns: (upper, middle, lower)
    """
    middle = sma(series, period)
    std = series.rolling(window=period, min_periods=period).std()
    upper = middle + num_std * std
    lower = middle - num_std * std
    return upper, middle, lower


def donchian_channel(
    high: pd.Series,
    low: pd.Series,
    period: int = 20,
) -> tuple[pd.Series, pd.Series]:
    """Donchian Channel.

    Returns: (upper, lower)
    """
    upper = high.rolling(window=period, min_periods=period).max()
    lower = low.rolling(window=period, min_periods=period).min()
    return upper, lower


# ──────────────────────────────────────────────────────────────
#  TradingView Community Popular Indicators
# ──────────────────────────────────────────────────────────────


def squeeze_momentum(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    bb_period: int = 20,
    bb_mult: float = 2.0,
    kc_period: int = 20,
    kc_mult: float = 1.5,
    mom_period: int = 20,
) -> tuple[pd.Series, pd.Series]:
    """Squeeze Momentum Indicator (LazyBear).

    Detects when Bollinger Bands are inside Keltner Channels (squeeze).
    Momentum is the linear regression value of price deviation.

    Returns: (squeeze_on, momentum)
        squeeze_on: bool Series, True when BB inside KC (compression)
        momentum: float Series, momentum oscillator value
    """
    bb_mid = close.rolling(bb_period, min_periods=bb_period).mean()
    bb_std = close.rolling(bb_period, min_periods=bb_period).std()
    bb_upper = bb_mid + bb_mult * bb_std
    bb_lower = bb_mid - bb_mult * bb_std

    kc_mid = close.rolling(kc_period, min_periods=kc_period).mean()
    atr_val = atr(high, low, close, kc_period)
    kc_upper = kc_mid + kc_mult * atr_val
    kc_lower = kc_mid - kc_mult * atr_val

    squeeze_on = (bb_lower > kc_lower) & (bb_upper < kc_upper)

    highest = high.rolling(mom_period, min_periods=mom_period).max()
    lowest = low.rolling(mom_period, min_periods=mom_period).min()
    midline = (highest + lowest) / 2.0
    midline = (midline + close.rolling(mom_period, min_periods=mom_period).mean()) / 2.0
    val = close - midline

    # Vectorized linear regression value at last point of each window
    P = mom_period
    x = np.arange(P, dtype=float)
    sx = x.sum()
    sxx = (x ** 2).sum()
    denom = P * sxx - sx * sx

    y_sum = val.rolling(P, min_periods=P).sum()
    xy_sum = val.rolling(P, min_periods=P).apply(
        lambda w: (x * w).sum(), raw=True,
    )
    slope = (P * xy_sum - sx * y_sum) / denom
    intercept = (y_sum - slope * sx) / P
    momentum = intercept + slope * (P - 1)

    return squeeze_on, momentum


def wavetrend(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    channel_period: int = 10,
    avg_period: int = 21,
    signal_period: int = 4,
) -> tuple[pd.Series, pd.Series]:
    """WaveTrend Oscillator (LazyBear).

    Returns: (wt1, wt2)
        wt1: main oscillator line
        wt2: signal line (SMA of wt1)
    """
    ap = (high + low + close) / 3.0
    esa = ema(ap, channel_period)
    d = ema((ap - esa).abs(), channel_period)
    ci = (ap - esa) / (0.015 * d.replace(0, np.nan))
    ci = ci.fillna(0)
    wt1 = ema(ci, avg_period)
    wt2 = sma(wt1, signal_period)
    return wt1, wt2


def supertrend(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 10,
    multiplier: float = 3.0,
) -> tuple[pd.Series, pd.Series]:
    """Supertrend Indicator.

    Returns: (supertrend_line, direction)
        supertrend_line: the supertrend value
        direction: +1 for uptrend (bullish), -1 for downtrend (bearish)
    """
    hl2 = (high + low) / 2.0
    atr_val = atr(high, low, close, period)

    ub = (hl2 + multiplier * atr_val).values.copy()
    lb = (hl2 - multiplier * atr_val).values.copy()
    c = close.values
    n = len(c)
    st_arr = np.full(n, np.nan)
    dir_arr = np.zeros(n, dtype=int)

    for i in range(period, n):
        if np.isnan(ub[i]) or np.isnan(lb[i]):
            continue
        if i > period:
            if not np.isnan(lb[i - 1]) and c[i - 1] > lb[i - 1]:
                lb[i] = max(lb[i], lb[i - 1])
            if not np.isnan(ub[i - 1]) and c[i - 1] < ub[i - 1]:
                ub[i] = min(ub[i], ub[i - 1])
        if i == period:
            dir_arr[i] = 1 if c[i] > ub[i] else -1
        else:
            if dir_arr[i - 1] == 1:
                dir_arr[i] = -1 if c[i] < lb[i] else 1
            else:
                dir_arr[i] = 1 if c[i] > ub[i] else -1
        st_arr[i] = lb[i] if dir_arr[i] == 1 else ub[i]

    st = pd.Series(st_arr, index=close.index)
    direction = pd.Series(dir_arr, index=close.index, dtype=int)
    return st, direction


def vwap(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    volume: pd.Series,
    datetimes: pd.Series | None = None,
) -> pd.Series:
    """Volume Weighted Average Price (VWAP).

    If datetimes is provided, VWAP resets at the start of each trading day.

    Returns: vwap Series
    """
    typical = (high + low + close) / 3.0
    tp_vol = typical * volume

    if datetimes is not None:
        result = pd.Series(np.nan, index=close.index)
        cum_tp_vol = 0.0
        cum_vol = 0.0
        prev_date = None

        for i in range(len(close)):
            dt = datetimes.iloc[i]
            current_date = dt.date() if hasattr(dt, 'date') else dt
            if prev_date is not None and current_date != prev_date:
                cum_tp_vol = 0.0
                cum_vol = 0.0
            cum_tp_vol += tp_vol.iloc[i]
            cum_vol += volume.iloc[i]
            result.iloc[i] = cum_tp_vol / cum_vol if cum_vol > 0 else typical.iloc[i]
            prev_date = current_date
        return result
    else:
        cum_tp_vol = tp_vol.cumsum()
        cum_vol = volume.cumsum()
        return cum_tp_vol / cum_vol.replace(0, np.nan)


def adx(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 14,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Average Directional Index (ADX).

    Returns: (adx_line, plus_di, minus_di)
        adx_line: ADX value (0-100, >25 = trending)
        plus_di: +DI line
        minus_di: -DI line
    """
    prev_high = high.shift(1)
    prev_low = low.shift(1)
    prev_close = close.shift(1)

    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)

    up_move = high - prev_high
    down_move = prev_low - low

    plus_dm = pd.Series(0.0, index=close.index)
    minus_dm = pd.Series(0.0, index=close.index)
    plus_dm[(up_move > down_move) & (up_move > 0)] = up_move
    minus_dm[(down_move > up_move) & (down_move > 0)] = down_move

    alpha = 1.0 / period
    atr_smooth = tr.ewm(alpha=alpha, min_periods=period, adjust=False).mean()
    plus_dm_smooth = plus_dm.ewm(alpha=alpha, min_periods=period, adjust=False).mean()
    minus_dm_smooth = minus_dm.ewm(alpha=alpha, min_periods=period, adjust=False).mean()

    plus_di = 100.0 * plus_dm_smooth / atr_smooth.replace(0, np.nan)
    minus_di = 100.0 * minus_dm_smooth / atr_smooth.replace(0, np.nan)

    di_sum = plus_di + minus_di
    di_diff = (plus_di - minus_di).abs()
    dx = 100.0 * di_diff / di_sum.replace(0, np.nan)

    adx_line = dx.ewm(alpha=alpha, min_periods=period, adjust=False).mean()

    adx_line.iloc[:period * 2] = np.nan
    plus_di.iloc[:period] = np.nan
    minus_di.iloc[:period] = np.nan

    return adx_line, plus_di, minus_di
