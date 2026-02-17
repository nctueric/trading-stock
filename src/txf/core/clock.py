"""Clock abstraction for time management.

SimulatedClock is used in backtesting (time controlled by the engine).
LiveClock is used in paper/live trading (real wall-clock time).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, time, timezone, timedelta
from typing import Optional

from txf.core.types import SessionType

# Taiwan timezone: UTC+8
TW_TZ = timezone(timedelta(hours=8))

# Trading session boundaries (Taiwan local time)
DAY_SESSION_START = time(8, 45)
DAY_SESSION_END = time(13, 45)
NIGHT_SESSION_START = time(15, 0)
NIGHT_SESSION_END = time(5, 0)  # Next calendar day


class Clock(ABC):
    """Abstract clock for time queries."""

    @abstractmethod
    def now(self) -> datetime:
        """Return the current time."""

    def session_type(self, dt: Optional[datetime] = None) -> SessionType:
        """Determine which trading session a given time falls into."""
        t = (dt or self.now()).time()
        if DAY_SESSION_START <= t <= DAY_SESSION_END:
            return SessionType.DAY
        return SessionType.NIGHT

    def is_trading_hours(self, dt: Optional[datetime] = None) -> bool:
        """Check if the given time is within trading hours."""
        t = (dt or self.now()).time()
        if DAY_SESSION_START <= t <= DAY_SESSION_END:
            return True
        if t >= NIGHT_SESSION_START or t <= NIGHT_SESSION_END:
            return True
        return False


class SimulatedClock(Clock):
    """Clock controlled by the backtest engine."""

    def __init__(self, start_time: Optional[datetime] = None) -> None:
        self._current_time = start_time or datetime(2024, 1, 1, 8, 45)

    def now(self) -> datetime:
        return self._current_time

    def advance_to(self, dt: datetime) -> None:
        """Set the clock to a specific time (called by the engine)."""
        self._current_time = dt


class LiveClock(Clock):
    """Real wall-clock time for live/paper trading."""

    def now(self) -> datetime:
        return datetime.now(TW_TZ).replace(tzinfo=None)
