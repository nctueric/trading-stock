"""Core data types shared across all modules.

All price-related fields use Decimal for financial precision.
Dataclasses are frozen where immutability is desired (Bar, Fill, OrderRequest).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional


class Side(Enum):
    BUY = "BUY"
    SELL = "SELL"

    @property
    def opposite(self) -> Side:
        return Side.SELL if self == Side.BUY else Side.BUY


class PriceType(Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"


class OrderStatus(Enum):
    PENDING = "PENDING"
    SUBMITTED = "SUBMITTED"
    FILLED = "FILLED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


class SessionType(Enum):
    DAY = "DAY"      # 日盤 08:45 - 13:45
    NIGHT = "NIGHT"  # 夜盤 15:00 - 05:00


@dataclass(frozen=True)
class Bar:
    """OHLCV bar (K-line) data."""

    symbol: str
    datetime: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    open_interest: Optional[int] = None
    session: SessionType = SessionType.DAY


@dataclass(frozen=True)
class Tick:
    """Single tick (trade) data."""

    symbol: str
    datetime: datetime
    price: Decimal
    volume: int
    side: Optional[Side] = None
    session: SessionType = SessionType.DAY


@dataclass(frozen=True)
class OrderRequest:
    """An order to be submitted (immutable once created)."""

    id: str
    symbol: str
    side: Side
    quantity: int
    price_type: PriceType
    price: Optional[Decimal] = None
    stop_price: Optional[Decimal] = None
    timestamp: Optional[datetime] = None


@dataclass(frozen=True)
class Fill:
    """A confirmed trade execution."""

    order_id: str
    symbol: str
    side: Side
    price: Decimal
    quantity: int
    commission: Decimal
    tax: Decimal
    timestamp: datetime


@dataclass
class Position:
    """A current open position in a single symbol."""

    symbol: str
    side: Side
    quantity: int
    avg_price: Decimal
    unrealized_pnl: Decimal = Decimal("0")
    margin_required: Decimal = Decimal("0")

    @property
    def is_long(self) -> bool:
        return self.side == Side.BUY

    @property
    def is_short(self) -> bool:
        return self.side == Side.SELL


@dataclass
class PortfolioState:
    """Snapshot of the entire portfolio at a point in time."""

    cash: Decimal
    positions: dict[str, Position] = field(default_factory=dict)
    total_equity: Decimal = Decimal("0")
    used_margin: Decimal = Decimal("0")
    available_margin: Decimal = Decimal("0")
    realized_pnl: Decimal = Decimal("0")
    unrealized_pnl: Decimal = Decimal("0")


@dataclass(frozen=True)
class TradeRecord:
    """A completed round-trip trade (entry + exit) for reporting."""

    symbol: str
    side: Side
    entry_price: Decimal
    exit_price: Decimal
    quantity: int
    entry_time: datetime
    exit_time: datetime
    pnl: Decimal
    commission: Decimal
    tax: Decimal
    bars_held: int = 0
