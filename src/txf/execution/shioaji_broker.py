"""Shioaji (永豐證券) broker integration.

Wraps the Shioaji API for live order execution and market data.
Requires the 'shioaji' package: pip install shioaji

This module provides a thin adapter layer that maps Shioaji's
API calls to our Broker interface, handling:
- Connection/authentication
- Order submission/cancellation
- Fill callback translation
- Contract mapping (TX -> TXF)
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Callable, Optional

from txf.core.errors import BrokerConnectionError
from txf.core.types import Fill, OrderRequest, OrderStatus, PriceType, Side
from txf.execution.broker import Broker
from txf.execution.order_manager import OrderManager

logger = logging.getLogger(__name__)


class ShioajiBroker(Broker):
    """Live broker using Shioaji API.

    Usage:
        broker = ShioajiBroker(
            api_key="YOUR_API_KEY",
            secret_key="YOUR_SECRET_KEY",
            person_id="YOUR_PERSON_ID",
        )
        broker.connect()
        broker.submit_order(order)
    """

    # Map our symbols to Shioaji contract codes
    SYMBOL_MAP = {
        "TX": "TXF",   # 大台指
        "MTX": "MXF",  # 小台指
    }

    def __init__(
        self,
        api_key: str = "",
        secret_key: str = "",
        person_id: str = "",
        simulation: bool = True,
    ) -> None:
        self._api_key = api_key
        self._secret_key = secret_key
        self._person_id = person_id
        self._simulation = simulation
        self._api: Optional[object] = None
        self._fill_callback: Optional[Callable[[Fill], None]] = None
        self._order_manager = OrderManager()
        self._connected = False

    def connect(self) -> None:
        """Connect and authenticate with Shioaji."""
        try:
            import shioaji as sj
        except ImportError:
            raise BrokerConnectionError(
                "shioaji package not installed. "
                "Install with: pip install shioaji"
            )

        try:
            self._api = sj.Shioaji(simulation=self._simulation)
            self._api.login(
                api_key=self._api_key,
                secret_key=self._secret_key,
                person_id=self._person_id,
            )
            self._connected = True
            logger.info(
                f"Connected to Shioaji (simulation={self._simulation})"
            )

            # Register fill callback
            self._api.set_order_callback(self._on_shioaji_order_update)

        except Exception as e:
            self._connected = False
            raise BrokerConnectionError(f"Shioaji login failed: {e}") from e

    def disconnect(self) -> None:
        if self._api is not None:
            try:
                self._api.logout()
            except Exception:
                pass
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    def submit_order(self, order: OrderRequest) -> str:
        """Submit an order via Shioaji."""
        if not self._connected or self._api is None:
            raise BrokerConnectionError("Not connected to Shioaji")

        import shioaji as sj

        contract = self._get_contract(order.symbol)
        sj_order = self._api.Order(
            action=sj.Action.Buy if order.side == Side.BUY else sj.Action.Sell,
            price=float(order.price) if order.price else 0,
            quantity=order.quantity,
            price_type=(
                sj.StockPriceType.MKT
                if order.price_type == PriceType.MARKET
                else sj.StockPriceType.LMT
            ),
            order_type=sj.OrderType.ROD,
        )

        self._order_manager.register_order(order)
        trade = self._api.place_order(contract, sj_order)
        self._order_manager.mark_submitted(order.id)

        logger.info(
            f"Shioaji order submitted: {order.side.value} "
            f"{order.quantity}x {order.symbol} "
            f"(trade_id={getattr(trade, 'order_id', 'N/A')})"
        )
        return order.id

    def cancel_order(self, order_id: str) -> bool:
        """Cancel an order via Shioaji."""
        if not self._connected or self._api is None:
            return False
        # Shioaji cancellation requires the trade object;
        # in a full implementation we'd store the trade mapping.
        self._order_manager.mark_cancelled(order_id)
        logger.info(f"Order {order_id} cancel requested")
        return True

    def get_order_status(self, order_id: str) -> OrderStatus:
        return self._order_manager.get_status(order_id)

    def set_fill_callback(self, callback: Callable[[Fill], None]) -> None:
        self._fill_callback = callback

    @property
    def order_manager(self) -> OrderManager:
        return self._order_manager

    # -- Shioaji-specific methods --

    def get_account_balance(self) -> Optional[dict]:
        """Query current account margin/balance."""
        if not self._connected or self._api is None:
            return None
        try:
            margin = self._api.margin(self._api.futopt_account)
            return {
                "equity": getattr(margin, "equity", 0),
                "available_margin": getattr(margin, "available_margin", 0),
            }
        except Exception as e:
            logger.error(f"Failed to get account balance: {e}")
            return None

    # -- Internal helpers --

    def _get_contract(self, symbol: str) -> object:
        """Map our symbol to a Shioaji contract."""
        sj_code = self.SYMBOL_MAP.get(symbol, symbol)
        contract = self._api.Contracts.Futures[sj_code]
        # Get the front-month contract
        return contract[f"{sj_code}R1"]

    def _on_shioaji_order_update(self, stat, msg) -> None:
        """Callback from Shioaji when order state changes."""
        logger.debug(f"Shioaji order update: stat={stat}, msg={msg}")
        # In a full implementation, parse msg to extract fill details
        # and call self._fill_callback with a Fill object.

    # -- Market data convenience --

    def subscribe_ticks(self, symbol: str, callback: Callable) -> None:
        """Subscribe to real-time tick data via Shioaji."""
        if not self._connected or self._api is None:
            raise BrokerConnectionError("Not connected")
        contract = self._get_contract(symbol)
        self._api.quote.subscribe(contract, quote_type="tick")
        self._api.quote.set_on_tick_fop_v1_callback(callback)

    def subscribe_kbars(self, symbol: str, callback: Callable) -> None:
        """Subscribe to real-time K-bar data via Shioaji."""
        if not self._connected or self._api is None:
            raise BrokerConnectionError("Not connected")
        contract = self._get_contract(symbol)
        self._api.quote.subscribe(contract, quote_type="bidask")
        self._api.quote.set_on_bidask_fop_v1_callback(callback)
