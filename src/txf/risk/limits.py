"""Position and exposure limit rules."""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from txf.core.types import OrderRequest, PortfolioState, Side


class LimitChecker:
    """Validates that orders and positions stay within defined limits."""

    def __init__(
        self,
        max_position_contracts: int = 10,
        max_total_exposure_pct: Decimal = Decimal("0.5"),
    ) -> None:
        self.max_position_contracts = max_position_contracts
        self.max_total_exposure_pct = max_total_exposure_pct

    def check_position_limit(
        self,
        order: OrderRequest,
        portfolio: PortfolioState,
    ) -> Optional[str]:
        """Check if an order would exceed position limits.

        Returns rejection reason or None if OK.
        """
        current_pos = portfolio.positions.get(order.symbol)
        current_qty = current_pos.quantity if current_pos else 0

        # If order is in same direction as existing position, check limit
        if current_pos and current_pos.side == order.side:
            new_qty = current_qty + order.quantity
        elif current_pos and current_pos.side != order.side:
            # Reducing or reversing - calculate net
            net_qty = current_qty - order.quantity
            new_qty = abs(net_qty)
        else:
            new_qty = order.quantity

        if new_qty > self.max_position_contracts:
            return (
                f"Position limit exceeded: {new_qty} > "
                f"{self.max_position_contracts} contracts"
            )
        return None

    def check_total_exposure(
        self,
        portfolio: PortfolioState,
    ) -> Optional[str]:
        """Check if total margin usage is within limits."""
        if portfolio.total_equity <= 0:
            return "Total equity is non-positive"
        pct = portfolio.used_margin / portfolio.total_equity
        if pct > self.max_total_exposure_pct:
            return (
                f"Exposure limit exceeded: {pct:.1%} > "
                f"{self.max_total_exposure_pct:.1%}"
            )
        return None
