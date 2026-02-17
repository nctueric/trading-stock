"""Real-time risk monitoring: drawdown, margin, daily P&L."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Optional

from txf.core.types import OrderRequest, PortfolioState, PriceType, Position


class RealtimeRiskMonitor:
    """Continuous risk monitoring during trading.

    Monitors:
    1. Max drawdown percentage (from peak equity)
    2. Maintenance margin breach
    3. Daily loss limit
    """

    def __init__(
        self,
        max_drawdown_pct: Decimal = Decimal("0.10"),
        max_daily_loss: Decimal = Decimal("100000"),
    ) -> None:
        self._max_drawdown_pct = max_drawdown_pct
        self._max_daily_loss = max_daily_loss
        self._peak_equity = Decimal("0")
        self._session_start_equity = Decimal("0")
        self._trading_halted = False

    def initialize(self, initial_equity: Decimal) -> None:
        """Set initial values at the start of a backtest or session."""
        self._peak_equity = initial_equity
        self._session_start_equity = initial_equity

    def update(self, portfolio: PortfolioState) -> list[str]:
        """Check risk conditions and return list of warnings/breaches.

        Returns list of warning messages (empty if all OK).
        """
        warnings: list[str] = []

        # Update peak equity
        if portfolio.total_equity > self._peak_equity:
            self._peak_equity = portfolio.total_equity

        # 1. Drawdown check
        if self._peak_equity > 0:
            drawdown = (
                (self._peak_equity - portfolio.total_equity) / self._peak_equity
            )
            if drawdown >= self._max_drawdown_pct:
                self._trading_halted = True
                warnings.append(
                    f"DRAWDOWN BREACH: {drawdown:.2%} >= "
                    f"{self._max_drawdown_pct:.2%}"
                )

        # 2. Maintenance margin check
        for sym, pos in portfolio.positions.items():
            if pos.margin_required > 0 and pos.quantity > 0:
                # Check if equity covers maintenance margin
                if portfolio.total_equity < portfolio.used_margin * Decimal("0.75"):
                    warnings.append(
                        f"MARGIN CALL: equity {portfolio.total_equity} < "
                        f"maintenance margin for {sym}"
                    )

        # 3. Daily loss check
        daily_pnl = portfolio.total_equity - self._session_start_equity
        if daily_pnl <= -self._max_daily_loss:
            self._trading_halted = True
            warnings.append(
                f"DAILY LOSS LIMIT: {daily_pnl} <= -{self._max_daily_loss}"
            )

        return warnings

    @property
    def is_trading_halted(self) -> bool:
        return self._trading_halted

    def should_force_close(self) -> bool:
        """Whether we should force-close all positions."""
        return self._trading_halted

    def reset_session(self, equity: Decimal) -> None:
        """Reset daily tracking for a new session."""
        self._session_start_equity = equity
        self._trading_halted = False

    @property
    def current_drawdown_pct(self) -> Decimal:
        if self._peak_equity <= 0:
            return Decimal("0")
        return (self._peak_equity - self._peak_equity) / self._peak_equity
