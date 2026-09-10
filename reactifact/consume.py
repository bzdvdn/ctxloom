from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from .artifacts import Artifact, ArtifactType
from .events import EventType
from .triggers import Trigger


class Consume:
    """Describes the consumed artifact type, condition and triggering events.

    All parameters can be set as class attributes (for inheritance)
    or passed to the constructor.
    """

    artifact_type: ArtifactType | None = None
    condition: Callable[[Artifact[Any]], bool] | None = None
    event_types: Sequence[EventType] = (
        EventType.ARTIFACT_CREATED,
        EventType.ARTIFACT_UPDATED,
    )

    def __init__(
        self,
        artifact_type: ArtifactType | None = None,
        condition: Callable[[Artifact[Any]], bool] | None = None,
        event_types: Sequence[EventType] | None = None,
    ):
        self.artifact_type = artifact_type or self.__class__.artifact_type
        if self.artifact_type is None:
            raise ValueError(
                "artifact_type must be provided either as class attribute or constructor argument"
            )

        self.condition = (
            condition if condition is not None else self.__class__.condition
        )
        self.event_types = list(
            event_types if event_types is not None else self.__class__.event_types
        )

    def to_triggers(self) -> list[Trigger]:
        """Converts into a list of triggers for automatic reaction."""
        return [
            Trigger(event_type, self.artifact_type, self.condition)
            for event_type in self.event_types
        ]

    @classmethod
    def by_status(
        cls,
        artifact_type: ArtifactType,
        status: str,
        event_types: Sequence[EventType] = (
            EventType.ARTIFACT_CREATED,
            EventType.ARTIFACT_UPDATED,
        ),
    ) -> Consume:
        """Creates a Consume with a condition on the equality of the status field."""
        return cls(
            artifact_type,
            condition=lambda art: getattr(art.data, "status", None) == status,
            event_types=event_types,
        )

    @classmethod
    def by_field(
        cls,
        artifact_type: ArtifactType,
        field: str,
        value: Any,
        event_types: Sequence[EventType] = (
            EventType.ARTIFACT_CREATED,
            EventType.ARTIFACT_UPDATED,
        ),
    ) -> Consume:
        """Creates a Consume with a condition on the equality of an arbitrary field."""
        return cls(
            artifact_type,
            condition=lambda art: getattr(art.data, field, None) == value,
            event_types=event_types,
        )


def consume(
    artifact_type: ArtifactType,
    condition: Callable[[Artifact[Any]], bool] | None = None,
    event_types: Sequence[EventType] = (
        EventType.ARTIFACT_CREATED,
        EventType.ARTIFACT_UPDATED,
    ),
) -> Consume:
    """Factory for quickly creating a Consume."""
    return Consume(artifact_type, condition, event_types)
