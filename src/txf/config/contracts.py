"""Contract specifications for Taiwan futures."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from decimal import Decimal
from typing import Optional

from txf.core.constants import (
    MTX_INITIAL_MARGIN,
    MTX_MAINTENANCE_MARGIN,
    MTX_MULTIPLIER,
    MTX_TICK_SIZE,
    TX_INITIAL_MARGIN,
    TX_MAINTENANCE_MARGIN,
    TX_MULTIPLIER,
    TX_TICK_SIZE,
)
from txf.core.errors import ContractNotFoundError


@dataclass(frozen=True)
class TradingSession:
    """Trading session time boundaries."""

    start: time
    end: time
    name: str


@dataclass(frozen=True)
class ContractSpec:
    """Specification for a futures contract."""

    symbol: str
    name: str
    multiplier: Decimal
    tick_size: Decimal
    currency: str
    initial_margin: Decimal
    maintenance_margin: Decimal
    day_session: TradingSession
    night_session: Optional[TradingSession] = None

    @property
    def tick_value(self) -> Decimal:
        """Value of one tick move in currency terms."""
        return self.tick_size * self.multiplier


# Pre-built specs for TX and MTX
TX_DAY = TradingSession(start=time(8, 45), end=time(13, 45), name="日盤")
TX_NIGHT = TradingSession(start=time(15, 0), end=time(5, 0), name="夜盤")

TX_SPEC = ContractSpec(
    symbol="TX",
    name="臺股期貨",
    multiplier=TX_MULTIPLIER,
    tick_size=TX_TICK_SIZE,
    currency="TWD",
    initial_margin=TX_INITIAL_MARGIN,
    maintenance_margin=TX_MAINTENANCE_MARGIN,
    day_session=TX_DAY,
    night_session=TX_NIGHT,
)

MTX_SPEC = ContractSpec(
    symbol="MTX",
    name="小型臺指期貨",
    multiplier=MTX_MULTIPLIER,
    tick_size=MTX_TICK_SIZE,
    currency="TWD",
    initial_margin=MTX_INITIAL_MARGIN,
    maintenance_margin=MTX_MAINTENANCE_MARGIN,
    day_session=TX_DAY,
    night_session=TX_NIGHT,
)


class ContractRegistry:
    """Lookup table for contract specifications."""

    def __init__(self) -> None:
        self._specs: dict[str, ContractSpec] = {
            "TX": TX_SPEC,
            "MTX": MTX_SPEC,
        }

    def get(self, symbol: str) -> ContractSpec:
        """Get contract spec by symbol prefix (e.g. 'TX', 'MTX')."""
        base = self._resolve_base_symbol(symbol)
        spec = self._specs.get(base)
        if spec is None:
            raise ContractNotFoundError(f"Unknown contract: {symbol}")
        return spec

    def register(self, spec: ContractSpec) -> None:
        """Register a custom contract specification."""
        self._specs[spec.symbol] = spec

    def _resolve_base_symbol(self, symbol: str) -> str:
        """Resolve a full symbol (e.g. 'TXFG5') to base ('TX')."""
        # Check longest prefix first to avoid 'TX' matching 'TXO'
        for prefix in sorted(self._specs.keys(), key=len, reverse=True):
            if symbol.startswith(prefix):
                return prefix
        return symbol
