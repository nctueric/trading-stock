"""Stateless P&L and margin calculation utilities."""

from __future__ import annotations

from decimal import Decimal

from txf.config.contracts import ContractSpec
from txf.core.types import Side


def calculate_unrealized_pnl(
    side: Side,
    avg_price: Decimal,
    current_price: Decimal,
    quantity: int,
    multiplier: Decimal,
) -> Decimal:
    """Calculate unrealized P&L for an open position.

    For long:  (current - avg) * qty * multiplier
    For short: (avg - current) * qty * multiplier
    """
    if side == Side.BUY:
        return (current_price - avg_price) * quantity * multiplier
    else:
        return (avg_price - current_price) * quantity * multiplier


def calculate_realized_pnl(
    side: Side,
    entry_price: Decimal,
    exit_price: Decimal,
    quantity: int,
    multiplier: Decimal,
) -> Decimal:
    """Calculate realized P&L for a closed trade."""
    if side == Side.BUY:
        return (exit_price - entry_price) * quantity * multiplier
    else:
        return (entry_price - exit_price) * quantity * multiplier


def calculate_margin_required(
    quantity: int,
    spec: ContractSpec,
) -> Decimal:
    """Calculate initial margin required for a position."""
    return spec.initial_margin * quantity


def calculate_maintenance_margin(
    quantity: int,
    spec: ContractSpec,
) -> Decimal:
    """Calculate maintenance margin for a position."""
    return spec.maintenance_margin * quantity


def calculate_notional_value(
    price: Decimal,
    quantity: int,
    multiplier: Decimal,
) -> Decimal:
    """Calculate notional value of a position (for tax calculation)."""
    return price * quantity * multiplier
