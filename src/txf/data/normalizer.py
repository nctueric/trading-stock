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


def build_continuous_contract(
    bars_by_month: dict[str, list[Bar]],
    method: str = "back_adjust",
) -> list[Bar]:
    """Build a continuous futures contract from individual delivery months.

    Args:
        bars_by_month: Dict mapping contract code (e.g. "202403") to
                       list of Bar objects for that delivery month.
        method: "back_adjust" adjusts historical prices by the gap at
                each roll date. "unadjusted" simply concatenates.

    Returns:
        Single list of Bars representing the continuous contract.

    Rollover rule:
        Switch to the next month's contract on the last trading day
        where both contracts have data (typically 2-3 days before expiry).
    """
    if not bars_by_month:
        return []

    # Sort months chronologically
    sorted_months = sorted(bars_by_month.keys())

    if method == "unadjusted":
        # Simply take the front-month data and concatenate
        result: list[Bar] = []
        for month_key in sorted_months:
            result.extend(bars_by_month[month_key])
        result.sort(key=lambda b: b.datetime)
        # Deduplicate by datetime (keep the first = front month)
        seen_dt: set[datetime] = set()
        deduped: list[Bar] = []
        for bar in result:
            if bar.datetime not in seen_dt:
                seen_dt.add(bar.datetime)
                deduped.append(bar)
        return deduped

    # back_adjust method
    # Back-adjustment means the LATEST month is unadjusted (anchor),
    # and earlier months get shifted by the accumulated roll gaps.

    # 1. Build per-month lookup indexed by date
    month_data: dict[str, dict[datetime, Bar]] = {}
    for month_key in sorted_months:
        month_data[month_key] = {b.datetime: b for b in bars_by_month[month_key]}

    # 2. Compute roll gaps and roll dates (walking forward)
    roll_gaps: list[Decimal] = []  # gap[i] = gap at roll from month i to i+1
    roll_dates: list[Optional[datetime]] = []

    for i in range(len(sorted_months) - 1):
        current = sorted_months[i]
        next_m = sorted_months[i + 1]
        next_dates = set(month_data[next_m].keys())
        overlap = sorted(dt for dt in month_data[current] if dt in next_dates)

        if overlap:
            roll_dt = overlap[-1]
            gap = month_data[next_m][roll_dt].close - month_data[current][roll_dt].close
        else:
            roll_dt = sorted(month_data[current].keys())[-1] if month_data[current] else None
            gap = Decimal("0")

        roll_gaps.append(gap)
        roll_dates.append(roll_dt)

    # 3. Compute per-month adjustments (sum of all LATER gaps)
    # The latest month has adjustment=0; each earlier month accumulates
    adjustments: list[Decimal] = [Decimal("0")] * len(sorted_months)
    for i in range(len(sorted_months) - 2, -1, -1):
        adjustments[i] = adjustments[i + 1] + roll_gaps[i]

    # 4. Apply adjustments and collect bars
    all_adjusted: list[Bar] = []

    for i, month_key in enumerate(sorted_months):
        bars = sorted(bars_by_month[month_key], key=lambda b: b.datetime)
        adj = adjustments[i]
        roll_date = roll_dates[i] if i < len(roll_dates) else None

        for bar in bars:
            if roll_date is not None and bar.datetime > roll_date:
                continue  # After roll date, next month takes over
            adjusted = Bar(
                symbol=bar.symbol,
                datetime=bar.datetime,
                open=bar.open - adj,
                high=bar.high - adj,
                low=bar.low - adj,
                close=bar.close - adj,
                volume=bar.volume,
                open_interest=bar.open_interest,
                session=bar.session,
            )
            all_adjusted.append(adjusted)

    all_adjusted.sort(key=lambda b: b.datetime)

    # Deduplicate
    seen_dt2: set[datetime] = set()
    final: list[Bar] = []
    for bar in all_adjusted:
        if bar.datetime not in seen_dt2:
            seen_dt2.add(bar.datetime)
            final.append(bar)
    return final


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
