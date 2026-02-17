"""Custom exception hierarchy for the txf package."""


class TxfError(Exception):
    """Base exception for the txf package."""


class ConfigError(TxfError):
    """Invalid configuration."""


class DataError(TxfError):
    """Data fetching, parsing, or storage failure."""


class InsufficientMarginError(TxfError):
    """Order rejected due to insufficient margin."""


class RiskLimitBreached(TxfError):
    """A risk limit was breached (drawdown, position size, etc.)."""


class OrderRejectedError(TxfError):
    """Order rejected by pre-trade risk check or exchange."""

    def __init__(self, reason: str, order_id: str = "") -> None:
        self.reason = reason
        self.order_id = order_id
        super().__init__(f"Order {order_id} rejected: {reason}")


class BrokerConnectionError(TxfError):
    """Failed to connect to broker API."""


class ContractNotFoundError(TxfError):
    """Unknown contract symbol."""
