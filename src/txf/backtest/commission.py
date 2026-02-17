"""Commission and tax model for Taiwan futures."""

from __future__ import annotations

from decimal import Decimal

from txf.core.constants import DEFAULT_COMMISSION_PER_CONTRACT, DEFAULT_TAX_RATE


class CommissionModel:
    """Calculate trading costs for Taiwan futures.

    Costs per trade:
    - Commission: fixed amount per contract per side (default: 60 TWD)
    - Tax (期交稅): notional value × tax rate (default: 0.00002)
    """

    def __init__(
        self,
        commission_per_contract: Decimal = DEFAULT_COMMISSION_PER_CONTRACT,
        tax_rate: Decimal = DEFAULT_TAX_RATE,
    ) -> None:
        self.commission_per_contract = commission_per_contract
        self.tax_rate = tax_rate

    def calculate_commission(self, quantity: int) -> Decimal:
        """Commission for trading `quantity` contracts."""
        return self.commission_per_contract * quantity

    def calculate_tax(self, notional_value: Decimal) -> Decimal:
        """Tax on the notional value of the trade."""
        return notional_value * self.tax_rate

    def total_cost(self, quantity: int, notional_value: Decimal) -> Decimal:
        """Total trading cost (commission + tax)."""
        return self.calculate_commission(quantity) + self.calculate_tax(
            notional_value
        )
