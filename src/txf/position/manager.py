"""Position manager: tracks open positions, applies fills, computes portfolio state."""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from txf.config.contracts import ContractRegistry
from txf.core.types import Fill, Position, PortfolioState, Side, TradeRecord
from txf.position.calculator import (
    calculate_margin_required,
    calculate_unrealized_pnl,
    calculate_realized_pnl,
)


class PositionManager:
    """Manages positions, cash, and P&L with FIFO cost basis.

    Handles five fill scenarios:
    1. New open (no existing position)
    2. Add to position (same direction)
    3. Partial close (reduce quantity)
    4. Full close (quantity goes to zero)
    5. Reverse (close + open opposite direction)
    """

    def __init__(
        self,
        initial_capital: Decimal,
        contract_registry: ContractRegistry,
    ) -> None:
        self._initial_capital = initial_capital
        self._cash = initial_capital
        self._contracts = contract_registry
        self._positions: dict[str, Position] = {}
        self._realized_pnl = Decimal("0")
        self._trade_records: list[TradeRecord] = []
        self._equity_curve: list[Decimal] = []

        # Track entry bars for time-based stops
        self._entry_bar_index: dict[str, int] = {}
        self._current_bar_index = 0

    def apply_fill(self, fill: Fill) -> None:
        """Process a fill and update position/cash accordingly."""
        spec = self._contracts.get(fill.symbol)
        existing = self._positions.get(fill.symbol)

        # Deduct commission and tax from cash
        self._cash -= fill.commission + fill.tax

        if existing is None or existing.quantity == 0:
            # Case 1: New open
            self._open_position(fill, spec.initial_margin)
        elif existing.side == fill.side:
            # Case 2: Add to existing position (same direction)
            self._add_to_position(fill, existing, spec.initial_margin)
        else:
            # Cases 3-5: Reducing, closing, or reversing
            self._reduce_or_reverse(fill, existing, spec)

    def mark_to_market(self, symbol: str, current_price: Decimal) -> None:
        """Update unrealized P&L for a symbol at the given price."""
        pos = self._positions.get(symbol)
        if pos is None or pos.quantity == 0:
            return
        spec = self._contracts.get(symbol)
        pos.unrealized_pnl = calculate_unrealized_pnl(
            pos.side, pos.avg_price, current_price, pos.quantity, spec.multiplier
        )
        pos.margin_required = calculate_margin_required(pos.quantity, spec)

    def snapshot_equity(self) -> None:
        """Record current equity for drawdown tracking."""
        self._equity_curve.append(self.total_equity)

    def get_position(self, symbol: str) -> Optional[Position]:
        pos = self._positions.get(symbol)
        if pos is not None and pos.quantity == 0:
            return None
        return pos

    def get_portfolio_state(self) -> PortfolioState:
        """Return full portfolio snapshot."""
        unrealized = sum(
            p.unrealized_pnl
            for p in self._positions.values()
            if p.quantity > 0
        )
        used_margin = sum(
            p.margin_required
            for p in self._positions.values()
            if p.quantity > 0
        )
        total_equity = self._cash + unrealized
        return PortfolioState(
            cash=self._cash,
            positions={
                k: v for k, v in self._positions.items() if v.quantity > 0
            },
            total_equity=total_equity,
            used_margin=used_margin,
            available_margin=total_equity - used_margin,
            realized_pnl=self._realized_pnl,
            unrealized_pnl=unrealized,
        )

    @property
    def total_equity(self) -> Decimal:
        unrealized = sum(
            p.unrealized_pnl for p in self._positions.values() if p.quantity > 0
        )
        return self._cash + unrealized

    @property
    def equity_curve(self) -> list[Decimal]:
        return list(self._equity_curve)

    @property
    def trade_records(self) -> list[TradeRecord]:
        return list(self._trade_records)

    @property
    def cash(self) -> Decimal:
        return self._cash

    def set_bar_index(self, index: int) -> None:
        """Update the current bar index (called by the engine)."""
        self._current_bar_index = index

    # -- Internal helpers --

    def _open_position(self, fill: Fill, initial_margin: Decimal) -> None:
        self._positions[fill.symbol] = Position(
            symbol=fill.symbol,
            side=fill.side,
            quantity=fill.quantity,
            avg_price=fill.price,
            margin_required=initial_margin * fill.quantity,
        )
        self._entry_bar_index[fill.symbol] = self._current_bar_index

    def _add_to_position(
        self, fill: Fill, pos: Position, initial_margin: Decimal
    ) -> None:
        # Weighted average price
        total_qty = pos.quantity + fill.quantity
        pos.avg_price = (
            (pos.avg_price * pos.quantity + fill.price * fill.quantity)
            / total_qty
        )
        pos.quantity = total_qty
        pos.margin_required = initial_margin * total_qty

    def _reduce_or_reverse(self, fill: Fill, pos: Position, spec: object) -> None:
        from txf.config.contracts import ContractSpec
        assert isinstance(spec, ContractSpec)

        close_qty = min(fill.quantity, pos.quantity)
        remaining_fill_qty = fill.quantity - close_qty

        # Realized P&L for the closed portion
        pnl = calculate_realized_pnl(
            pos.side, pos.avg_price, fill.price,
            close_qty, spec.multiplier,
        )
        self._realized_pnl += pnl
        self._cash += pnl

        # Record the trade
        entry_bar = self._entry_bar_index.get(fill.symbol, 0)
        self._trade_records.append(
            TradeRecord(
                symbol=fill.symbol,
                side=pos.side,
                entry_price=pos.avg_price,
                exit_price=fill.price,
                quantity=close_qty,
                entry_time=fill.timestamp,  # Approximation
                exit_time=fill.timestamp,
                pnl=pnl,
                commission=fill.commission,
                tax=fill.tax,
                bars_held=self._current_bar_index - entry_bar,
            )
        )

        new_qty = pos.quantity - close_qty
        if new_qty == 0 and remaining_fill_qty == 0:
            # Case 4: Full close
            pos.quantity = 0
            pos.unrealized_pnl = Decimal("0")
            pos.margin_required = Decimal("0")
        elif new_qty > 0:
            # Case 3: Partial close
            pos.quantity = new_qty
            pos.margin_required = spec.initial_margin * new_qty
        else:
            # Case 5: Reverse - close existing, open opposite
            pos.quantity = 0
            pos.unrealized_pnl = Decimal("0")
            pos.margin_required = Decimal("0")
            if remaining_fill_qty > 0:
                self._positions[fill.symbol] = Position(
                    symbol=fill.symbol,
                    side=fill.side,
                    quantity=remaining_fill_qty,
                    avg_price=fill.price,
                    margin_required=spec.initial_margin * remaining_fill_qty,
                )
                self._entry_bar_index[fill.symbol] = self._current_bar_index
