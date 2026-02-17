"""Event bus for decoupled communication between modules."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable


class EventType(Enum):
    BAR = "bar"
    TICK = "tick"
    ORDER_SUBMITTED = "order_submitted"
    ORDER_FILLED = "order_filled"
    ORDER_CANCELLED = "order_cancelled"
    ORDER_REJECTED = "order_rejected"
    POSITION_CHANGED = "position_changed"
    RISK_BREACH = "risk_breach"
    SESSION_START = "session_start"
    SESSION_END = "session_end"


@dataclass
class Event:
    """Wrapper for event data."""

    event_type: EventType
    data: Any


class EventBus:
    """Simple synchronous publish/subscribe event bus.

    In backtest mode, events are dispatched synchronously in the order
    they are published. This ensures deterministic replay.
    """

    def __init__(self) -> None:
        self._handlers: dict[EventType, list[Callable[[Event], None]]] = (
            defaultdict(list)
        )

    def subscribe(
        self, event_type: EventType, handler: Callable[[Event], None]
    ) -> None:
        """Register a handler for a specific event type."""
        self._handlers[event_type].append(handler)

    def unsubscribe(
        self, event_type: EventType, handler: Callable[[Event], None]
    ) -> None:
        """Remove a handler."""
        handlers = self._handlers[event_type]
        if handler in handlers:
            handlers.remove(handler)

    def publish(self, event_type: EventType, data: Any = None) -> None:
        """Dispatch an event to all registered handlers."""
        event = Event(event_type=event_type, data=data)
        for handler in self._handlers.get(event_type, []):
            handler(event)

    def clear(self) -> None:
        """Remove all subscriptions."""
        self._handlers.clear()
