from __future__ import annotations

from abc import ABC
from collections.abc import Sequence
from typing import Any

from .artifacts import Artifact
from .consume import Consume
from .context import Context
from .events import Event
from .patches import Patch
from .produce import Produce
from .triggers import Trigger


class Agent(ABC):  # noqa: B024 — interface without abstract methods, run() has a default
    """Base container: consumes some artifacts and produces others.

    If `run` is not overridden, automatically collects inputs according to
    consumes and calls produce on every produce, merging the patches.
    """

    name: str = ""
    consumes: Sequence[Consume] | None = None
    produces: Sequence[Produce[Any]] | None = None
    triggers: list[Trigger] = []
    # Run priority within a single generation: lower value runs earlier.
    # Useful for "finishers"/evaluators that logically run last (§24).
    priority: int = 0

    def __init__(
        self,
        name: str | None = None,
        triggers: list[Trigger] | None = None,
        priority: int | None = None,
    ):
        self.name = name or self.name or self.__class__.__name__

        self.priority = (
            priority if priority is not None else getattr(self.__class__, "priority", 0)
        )

        if triggers is not None:
            self.triggers = list(triggers)
        elif self.triggers:
            self.triggers = list(self.triggers)
        elif self.consumes is not None:
            self.triggers = self._generate_triggers_from_consumes()
        else:
            self.triggers = []

        self._validate_contracts()

    def _generate_triggers_from_consumes(self) -> list[Trigger]:
        result = []
        for c in self.consumes or []:
            result.extend(c.to_triggers())
        return result

    def _validate_contracts(self) -> None:
        if self.consumes is not None:
            for c in self.consumes:
                if not isinstance(c, Consume):
                    raise TypeError(
                        f"consumes must contain Consume instances, got {type(c)}"
                    )
        if self.produces is not None:
            for p in self.produces:
                if not isinstance(p, Produce):
                    raise TypeError(
                        f"produces must contain Produce instances, got {type(p)}"
                    )

    def matches(self, event: Event, context: Context | None = None) -> bool:
        return any(trigger.matches(event, context) for trigger in self.triggers)

    def collect_inputs(self, context: Context) -> list[Artifact[Any]]:
        """Public access to the consumed artifacts.

        Used by the runtime to record the reads linkage (provenance) on run.
        """
        return self._collect_inputs(context)

    def _collect_inputs(self, context: Context) -> list[Artifact[Any]]:
        """Collects all artifacts matching consumes and conditions."""
        if not self.consumes:
            return []
        inputs: list[Artifact[Any]] = []
        for c in self.consumes:
            artifacts = context.list_artifacts(c.artifact_type)
            if c.condition:
                artifacts = [a for a in artifacts if c.condition(a)]
            inputs.extend(artifacts)
        return inputs

    async def run(self, event: Event, context: Context) -> Patch | None:
        return await self.execute(context, event)

    async def execute(
        self, context: Context, event: Event | None = None
    ) -> Patch | None:
        """Runs the agent (usually on an event), collecting patches from produces.

        Produce factories receive the triggering event to know which artifact
        woke them; the event is optional — execute can be called without it.
        """
        if not self.produces:
            return None
        inputs = self._collect_inputs(context)
        combined_patch = Patch()
        for p in self.produces:
            patch = await p.produce(context, inputs, event)
            if patch is None:
                continue  # produce returned "no work" (None — same as an empty Patch)
            combined_patch.operations.extend(patch.operations)
        return combined_patch if not combined_patch.is_empty() else None
