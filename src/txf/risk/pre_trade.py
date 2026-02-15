"""Pre-trade risk checks: validate orders before submission."""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from txf.config.contracts import ContractRegistry
from txf.core.types import OrderRequest, PortfolioState
from txf.risk.limits import LimitChecker


class PreTradeRiskCheck:
    """Synchronous order validation before submission to the matching engine.

    Checks:
    1. Margin sufficiency
    2. Position limits
    3. Daily loss limits
    """

    def __init__(
        self,
        contract_registry: ContractRegistry,
        limit_checker: LimitChecker,
        max_daily_loss: Decimal = Decimal("100000"),
    ) -> None:
        self._contracts = contract_registry
        self._limits = limit_checker
        self._max_daily_loss = max_daily_loss
        self._daily_realized_pnl = Decimal("0")

    def check(
        self,
        order: OrderRequest,
        portfolio: PortfolioState,
    ) -> Optional[str]:
        """Run all pre-trade checks. Returns rejection reason or None."""
        # 1. Margin check
        reason = self._check_margin(order, portfolio)
        if reason:
            return reason

        # 2. Position limit
        reason = self._limits.check_position_limit(order, portfolio)
        if reason:
            return reason

        # 3. Daily loss limit
        reason = self._check_daily_loss(portfolio)
        if reason:
            return reason

        return None

    def update_daily_pnl(self, realized_pnl: Decimal) -> None:
        """Called when a trade is closed to track daily P&L."""
        self._daily_realized_pnl = realized_pnl

    def reset_daily(self) -> None:
        """Reset daily tracking (called at session start)."""
        self._daily_realized_pnl = Decimal("0")

    def _check_margin(
        self, order: OrderRequest, portfolio: PortfolioState
    ) -> Optional[str]:
        spec = self._contracts.get(order.symbol)
        # Check if existing position is being reduced (no additional margin)
        existing = portfolio.positions.get(order.symbol)
        if existing and existing.side != order.side:
            return None  # Reducing/closing doesn't require extra margin

        required = spec.initial_margin * order.quantity
        if required > portfolio.available_margin:
            return (
                f"Insufficient margin: need {required}, "
                f"available {portfolio.available_margin}"
            )
        return None

    def _check_daily_loss(self, portfolio: PortfolioState) -> Optional[str]:
        daily_loss = -self._daily_realized_pnl  # Positive means loss
        if daily_loss >= self._max_daily_loss:
            return (
                f"Daily loss limit reached: {daily_loss} >= "
                f"{self._max_daily_loss}"
            )
        return None
