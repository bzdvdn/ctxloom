from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class ProgressEvent:
    """Progress event that agents publish into the stream (aggregate statuses).

    Candidate kinds: "status" (Thinking…, Searching in …, Found N…, Composing answer…).
    The app renders them in the chat; `data` holds the details (source, count, …).
    """

    kind: str
    message: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "message": self.message,
            "data": self.data,
            "timestamp": self.timestamp.isoformat(),
        }


QueueEvent = asyncio.Queue[ProgressEvent]


class EventHub:
    """Broadcaster of agent status events into a single- or multi-stream.

    Publishing without subscribers is a no-op, so ordinary (non-streaming) runtime
    runs pay nothing for announce.
    """

    def __init__(self) -> None:
        self._subscribers: set[QueueEvent] = set()

    @property
    def has_subscribers(self) -> bool:
        return bool(self._subscribers)

    def subscribe(self) -> QueueEvent:
        queue: QueueEvent = asyncio.Queue()
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: QueueEvent) -> None:
        self._subscribers.discard(queue)

    def publish(self, event: ProgressEvent) -> None:
        for queue in self._subscribers:
            queue.put_nowait(event)
