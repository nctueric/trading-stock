"""Data feed abstractions.

DataFeed is the abstract interface; HistoricalFeed replays bars from a list.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from datetime import datetime
from typing import Optional

from txf.core.types import Bar


class DataFeed(ABC):
    """Abstract data feed that yields bars sequentially."""

    @abstractmethod
    def __iter__(self) -> Iterator[Bar]:
        """Iterate over bars in chronological order."""

    @abstractmethod
    def reset(self) -> None:
        """Reset the feed to the beginning (for re-runs)."""


class HistoricalFeed(DataFeed):
    """Replays a list of bars, with optional date filtering."""

    def __init__(
        self,
        bars: list[Bar],
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> None:
        self._all_bars = sorted(bars, key=lambda b: b.datetime)
        self._start = start_date
        self._end = end_date
        self._bars = self._filter(self._all_bars)

    def _filter(self, bars: list[Bar]) -> list[Bar]:
        filtered = bars
        if self._start:
            filtered = [b for b in filtered if b.datetime >= self._start]
        if self._end:
            filtered = [b for b in filtered if b.datetime <= self._end]
        return filtered

    def __iter__(self) -> Iterator[Bar]:
        return iter(self._bars)

    def __len__(self) -> int:
        return len(self._bars)

    def reset(self) -> None:
        self._bars = self._filter(self._all_bars)
