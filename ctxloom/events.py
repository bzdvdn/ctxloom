from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum


class EventType(StrEnum):
    ARTIFACT_CREATED = "artifact_created"
    ARTIFACT_UPDATED = "artifact_updated"
    ARTIFACT_DELETED = "artifact_deleted"


class Event:
    """A lightweight event referencing an artifact by id and type."""

    def __init__(
        self,
        type: EventType,
        artifact_type: type | str,
        artifact_id: str,
    ):
        self.type = type
        self.artifact_type = artifact_type
        self.artifact_id = artifact_id
        self.timestamp = datetime.now(UTC)

    def __repr__(self) -> str:
        type_name = (
            self.artifact_type.__name__
            if isinstance(self.artifact_type, type)
            else self.artifact_type
        )
        return f"<Event {self.type.value} {type_name} id={self.artifact_id}>"
