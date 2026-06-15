"""
Async Event Bus — lightweight internal pub/sub for module communication.

No Redis, no RabbitMQ, no external dependencies.
Uses asyncio.Queue for in-process event distribution.
"""

import asyncio
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Awaitable, Callable

Listener = Callable[[Any], Awaitable[None]]


class EventType(StrEnum):
    """All events that flow through the system."""
    # Ingestion
    FILE_DETECTED = "file_detected"
    FILE_INDEXED = "file_indexed"
    TELEMETRY_INGESTED = "telemetry_ingested"

    # Trip lifecycle
    TRIP_STARTED = "trip_started"
    TRIP_ENDED = "trip_ended"
    TRIP_UPDATED = "trip_updated"
    TRIPS_MERGED = "trips_merged"

    # Driving events
    EVENT_DETECTED = "event_detected"

    # Archive
    ARCHIVE_COMPLETED = "archive_completed"
    ARCHIVE_FAILED = "archive_failed"

    # Storage
    STORAGE_HEALTH_CHECK = "storage_health_check"

    # System
    SYSTEM_STARTUP = "system_startup"
    SYSTEM_SHUTDOWN = "system_shutdown"


@dataclass
class Event:
    """Base event envelope."""
    type: EventType
    data: Any
    timestamp: datetime = field(default_factory=datetime.now)


class EventBus:
    """Async publish/subscribe event bus.

    Usage:
        bus = EventBus()

        @bus.on(EventType.TELEMETRY_INGESTED)
        async def handle_telemetry(event: Event):
            ...

        await bus.emit(Event(EventType.TELEMETRY_INGESTED, snapshot))
    """

    def __init__(self):
        self._listeners: dict[EventType, list[Listener]] = defaultdict(list)
        self._queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=10000)
        self._running = False
        self._task: asyncio.Task | None = None

    def on(self, event_type: EventType) -> Callable[[Listener], Listener]:
        """Decorator to register a listener for an event type."""
        def decorator(fn: Listener) -> Listener:
            self._listeners[event_type].append(fn)
            return fn
        return decorator

    def subscribe(self, event_type: EventType, listener: Listener) -> None:
        """Register a listener function for an event type."""
        self._listeners[event_type].append(listener)

    async def emit(self, event: Event) -> None:
        """Publish an event to all registered listeners of its type."""
        await self._queue.put(event)

    async def start(self) -> None:
        """Start the event processing loop."""
        self._running = True
        self._task = asyncio.create_task(self._process())

    async def stop(self) -> None:
        """Stop the event processing loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _process(self) -> None:
        """Main event processing loop — dispatches events to listeners."""
        while self._running:
            try:
                event = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                listeners = self._listeners.get(event.type, [])
                results = await asyncio.gather(
                    *[listener(event) for listener in listeners],
                    return_exceptions=True,
                )
                for result in results:
                    if isinstance(result, Exception):
                        import logging
                        logging.getLogger("event_bus").error(
                            "Listener error for %s: %s", event.type, result
                        )
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception:
                import logging
                logging.getLogger("event_bus").exception("Event bus processing error")


# Application-wide singleton
event_bus = EventBus()
