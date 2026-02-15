"""CSV file loader for historical market data."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from txf.core.errors import DataError
from txf.core.types import Bar
from txf.data.normalizer import normalize_csv_kbar, normalize_taifex_daily


class CsvLoader:
    """Load bars from CSV files.

    Supports two formats:
    1. TAIFEX format (Chinese headers): auto-detected by column names
    2. Generic format: expects columns [datetime, open, high, low, close, volume]
    """

    def __init__(
        self,
        symbol: str = "TX",
        datetime_col: str = "datetime",
        datetime_format: str = "%Y-%m-%d %H:%M:%S",
        encoding: str = "utf-8",
    ) -> None:
        self._symbol = symbol
        self._datetime_col = datetime_col
        self._datetime_format = datetime_format
        self._encoding = encoding

    def load(self, file_path: str | Path) -> list[Bar]:
        """Load bars from a CSV file."""
        path = Path(file_path)
        if not path.exists():
            raise DataError(f"File not found: {path}")

        try:
            df = pd.read_csv(path, encoding=self._encoding)
        except Exception as e:
            raise DataError(f"Failed to read CSV: {e}") from e

        if df.empty:
            return []

        # Auto-detect TAIFEX format
        if "日期" in df.columns and "開盤價" in df.columns:
            return normalize_taifex_daily(df, self._symbol)

        # Generic format
        return normalize_csv_kbar(
            df,
            self._symbol,
            datetime_col=self._datetime_col,
            datetime_format=self._datetime_format,
        )
