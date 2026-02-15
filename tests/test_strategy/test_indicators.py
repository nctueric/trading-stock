"""Tests for technical indicators."""

import numpy as np
import pandas as pd

from txf.strategy.indicators import (
    sma,
    ema,
    rsi,
    macd,
    atr,
    bollinger_bands,
    donchian_channel,
)


def test_sma_basic():
    s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    result = sma(s, 3)
    assert np.isnan(result.iloc[0])
    assert np.isnan(result.iloc[1])
    assert result.iloc[2] == 2.0  # (1+2+3)/3
    assert result.iloc[3] == 3.0  # (2+3+4)/3
    assert result.iloc[4] == 4.0  # (3+4+5)/3


def test_ema_first_value():
    s = pd.Series([10.0] * 10)
    result = ema(s, 5)
    # All same values -> EMA should equal the value
    assert abs(result.iloc[-1] - 10.0) < 1e-10


def test_rsi_overbought():
    # Strongly rising prices -> RSI should be high
    s = pd.Series([float(i) for i in range(100)])
    result = rsi(s, 14)
    assert result.iloc[-1] > 90


def test_macd_returns_three_series():
    s = pd.Series(np.random.randn(100).cumsum() + 100)
    macd_line, signal_line, histogram = macd(s)
    assert len(macd_line) == 100
    assert len(signal_line) == 100
    assert len(histogram) == 100


def test_bollinger_bands_relation():
    s = pd.Series(np.random.randn(50).cumsum() + 100)
    upper, middle, lower = bollinger_bands(s, 20, 2.0)
    # After warmup, upper > middle > lower
    for i in range(20, 50):
        if not np.isnan(upper.iloc[i]):
            assert upper.iloc[i] >= middle.iloc[i]
            assert middle.iloc[i] >= lower.iloc[i]


def test_donchian_channel():
    high = pd.Series([10.0, 12.0, 11.0, 13.0, 12.0])
    low = pd.Series([8.0, 9.0, 7.0, 10.0, 9.0])
    upper, lower = donchian_channel(high, low, period=3)
    # At index 2: max(10,12,11)=12, min(8,9,7)=7
    assert upper.iloc[2] == 12.0
    assert lower.iloc[2] == 7.0
