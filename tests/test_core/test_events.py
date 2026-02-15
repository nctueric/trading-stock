"""Tests for the EventBus."""

from txf.core.events import EventBus, EventType


def test_publish_subscribe():
    bus = EventBus()
    received = []
    bus.subscribe(EventType.BAR, lambda e: received.append(e.data))
    bus.publish(EventType.BAR, "bar_data")
    assert received == ["bar_data"]


def test_unsubscribe():
    bus = EventBus()
    received = []
    handler = lambda e: received.append(e.data)
    bus.subscribe(EventType.BAR, handler)
    bus.unsubscribe(EventType.BAR, handler)
    bus.publish(EventType.BAR, "bar_data")
    assert received == []


def test_multiple_handlers():
    bus = EventBus()
    r1, r2 = [], []
    bus.subscribe(EventType.ORDER_FILLED, lambda e: r1.append(1))
    bus.subscribe(EventType.ORDER_FILLED, lambda e: r2.append(2))
    bus.publish(EventType.ORDER_FILLED)
    assert r1 == [1]
    assert r2 == [2]


def test_no_cross_talk():
    bus = EventBus()
    received = []
    bus.subscribe(EventType.BAR, lambda e: received.append("bar"))
    bus.publish(EventType.TICK, "tick_data")
    assert received == []
