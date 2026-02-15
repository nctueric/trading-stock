"""Data normalization utilities.

Handles conversion from raw source formats into canonical Bar types,
including ROC (Republic of China) date parsing used by TAIFEX.
"""

from __future__ import annotations

from datetime import datetime, time
from decimal import Decimal, InvalidOperation
from typing import Optional

import pandas as pd

from txf.core.clock import DAY_SESSION_END, DAY_SESSION_START
from txf.core.types import Bar, SessionType


def normalize_taifex_daily(raw_df: pd.DataFrame, symbol: str) -> list[Bar]:
    """Convert TAIFEX downloaded CSV into canonical Bar objects.

    Expected TAIFEX CSV columns (Chinese headers):
        日期, 契約, 到期月份(週別), 開盤價, 最高價, 最低價, 收盤價,
        成交量, 結算價, 未沖銷契約數, ...
    """
    bars: list[Bar] = []
    for _, row in raw_df.iterrows():
        dt = _parse_roc_date(str(row["日期"]).strip())
        if dt is None:
            continue
        try:
            bars.append(
                Bar(
                    symbol=symbol,
                    datetime=dt,
                    open=Decimal(str(row["開盤價"]).replace(",", "")),
                    high=Decimal(str(row["最高價"]).replace(",", "")),
                    low=Decimal(str(row["最低價"]).replace(",", "")),
                    close=Decimal(str(row["收盤價"]).replace(",", "")),
                    volume=int(str(row["成交量"]).replace(",", "")),
                    open_interest=_safe_int(row.get("未沖銷契約數")),
                    session=SessionType.DAY,
                )
            )
        except (InvalidOperation, ValueError):
            continue
    return bars


def normalize_csv_kbar(
    raw_df: pd.DataFrame,
    symbol: str,
    datetime_col: str = "datetime",
    datetime_format: str = "%Y-%m-%d %H:%M:%S",
) -> list[Bar]:
    """Generic CSV -> Bar normalizer for third-party data sources."""
    bars: list[Bar] = []
    for _, row in raw_df.iterrows():
        try:
            dt = datetime.strptime(str(row[datetime_col]), datetime_format)
            bars.append(
                Bar(
                    symbol=symbol,
                    datetime=dt,
                    open=Decimal(str(row["open"])),
                    high=Decimal(str(row["high"])),
                    low=Decimal(str(row["low"])),
                    close=Decimal(str(row["close"])),
                    volume=int(row["volume"]),
                    session=_infer_session(dt),
                )
            )
        except (InvalidOperation, ValueError, KeyError):
            continue
    return bars


def _parse_roc_date(date_str: str) -> Optional[datetime]:
    """Parse ROC date format: '113/01/15' -> datetime(2024, 1, 15)."""
    try:
        parts = date_str.split("/")
        year = int(parts[0]) + 1911
        month = int(parts[1])
        day = int(parts[2])
        return datetime(year, month, day)
    except (ValueError, IndexError):
        return None


def _infer_session(dt: datetime) -> SessionType:
    t = dt.time()
    if DAY_SESSION_START <= t <= DAY_SESSION_END:
        return SessionType.DAY
    return SessionType.NIGHT


def _safe_int(val: object) -> Optional[int]:
    try:
        return int(str(val).replace(",", ""))
    except (ValueError, TypeError):
        return None
