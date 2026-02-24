"""TAIFEX (台灣期貨交易所) public data fetcher.

Downloads daily OHLCV data from the TAIFEX open data API.
The data is available in CSV format with ROC (民國) date headers.
"""

from __future__ import annotations

import io
import logging
from datetime import datetime, timedelta, date
from typing import Optional

import pandas as pd

from txf.core.errors import DataError
from txf.core.types import Bar
from txf.data.normalizer import normalize_taifex_daily

logger = logging.getLogger(__name__)

# TAIFEX open data endpoint for futures daily trading data
TAIFEX_DAILY_URL = (
    "https://www.taifex.com.tw/cht/3/futDataDown"
)


class TaifexFetcher:
    """Fetch daily futures data from TAIFEX website.

    Downloads the official daily trading report from TAIFEX,
    which includes OHLCV + settlement price + open interest.

    Usage:
        fetcher = TaifexFetcher()
        bars = fetcher.fetch_daily("TX", date(2024, 1, 2), date(2024, 1, 31))
    """

    def __init__(self, timeout: int = 30) -> None:
        self._timeout = timeout

    def fetch_daily(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
    ) -> list[Bar]:
        """Fetch daily bars from TAIFEX for a date range.

        Args:
            symbol: Contract symbol (e.g. "TX", "MTX")
            start_date: Start date (inclusive)
            end_date: End date (inclusive)

        Returns:
            List of Bar objects sorted by date.

        Note:
            TAIFEX limits queries to 30 days per request.
            This method automatically chunks the range.
        """
        try:
            import requests
        except ImportError:
            raise DataError(
                "requests package is required for TAIFEX fetcher. "
                "Install with: pip install requests"
            )

        all_bars: list[Bar] = []
        current = start_date

        while current <= end_date:
            chunk_end = min(current + timedelta(days=29), end_date)
            logger.info(
                f"Fetching TAIFEX data: {symbol} {current} -> {chunk_end}"
            )

            bars = self._fetch_chunk(symbol, current, chunk_end)
            all_bars.extend(bars)

            current = chunk_end + timedelta(days=1)

        # Deduplicate by datetime
        seen = set()
        unique_bars = []
        for b in all_bars:
            key = (b.symbol, b.datetime)
            if key not in seen:
                seen.add(key)
                unique_bars.append(b)

        return sorted(unique_bars, key=lambda b: b.datetime)

    def _fetch_chunk(
        self,
        symbol: str,
        start: date,
        end: date,
    ) -> list[Bar]:
        """Fetch a single chunk (max 30 days) from TAIFEX."""
        import requests

        # Convert to ROC date format for the API
        commodity_map = {
            "TX": "TX",
            "MTX": "MTX",
        }
        commodity_id = commodity_map.get(symbol, symbol)

        # TAIFEX expects ROC year dates
        start_roc = self._to_roc_date_str(start)
        end_roc = self._to_roc_date_str(end)

        form_data = {
            "down_type": "1",  # Daily data
            "queryStartDate": start_roc,
            "queryEndDate": end_roc,
            "commodity_id": commodity_id,
        }

        try:
            resp = requests.post(
                TAIFEX_DAILY_URL,
                data=form_data,
                timeout=self._timeout,
            )
            resp.raise_for_status()
        except requests.RequestException as e:
            raise DataError(f"TAIFEX request failed: {e}") from e

        # Parse the CSV response
        try:
            content = resp.text
            if not content.strip() or "查無資料" in content:
                return []
            df = pd.read_csv(io.StringIO(content))
            return normalize_taifex_daily(df, symbol)
        except Exception as e:
            raise DataError(f"Failed to parse TAIFEX response: {e}") from e

    @staticmethod
    def _to_roc_date_str(d: date) -> str:
        """Convert a date to ROC format string: 'YYYY/MM/DD' with ROC year."""
        roc_year = d.year - 1911
        return f"{roc_year}/{d.month:02d}/{d.day:02d}"

    @staticmethod
    def _from_roc_date_str(s: str) -> Optional[date]:
        """Parse ROC date string back to a date."""
        try:
            parts = s.strip().split("/")
            year = int(parts[0]) + 1911
            return date(year, int(parts[1]), int(parts[2]))
        except (ValueError, IndexError):
            return None
