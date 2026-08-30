from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable
from typing import Any, Generic, TypeVar

from pydantic import BaseModel

from .artifacts import Artifact, ArtifactType
from .context import Context
from .effects import Effects
from .events import Event
from .patches import Patch

TOut = TypeVar("TOut", bound=BaseModel)


class Produce(Generic[TOut]):
    """Describes the produced artifact type and how it is created.

    You can subclass and override `produce`, or pass a factory.

    **Primary authoring surface — `self.effects`** (§24): a produce writes
    `self.effects.create/update/link/ask(...)` and returns `None`; the runtime
    compiles the slot into one atomic patch (commit + events + trace):

        async def produce(self, context, inputs, event=None) -> None:
            answer = self.effects.create(Answer(...), id="answer:q1")
            answer.link("supported_by", evidence)
            return None

    The factory (legacy) may instead return:
    - a Patch (used as is)
    - a single Pydantic model (turned into a Create)
    - a list of Pydantic models (a Create is created for each)
    - None or an empty list (empty Patch)

    The factory accepts (context, inputs) or (context, inputs, event) if it
    needs to know which event woke it up (for example, which of the input
    artifacts became the trigger). Whether it accepts event is determined from
    its signature once at creation.
    """

    artifact_type: ArtifactType | None = None
    factory: Callable[..., Any] | None = None

    def __init__(
        self,
        artifact_type: ArtifactType | None = None,
        factory: Callable[..., Any] | None = None,
    ):
        self.artifact_type = artifact_type or self.__class__.artifact_type
        if self.artifact_type is None:
            raise ValueError(
                "artifact_type must be provided either as class attribute or constructor argument"
            )
        self.factory = factory if factory is not None else self.__class__.factory
        self._accepts_event = False
        if self.factory is not None:
            try:
                signature = inspect.signature(self.factory)
            except (TypeError, ValueError):
                signature = None
            if signature is not None:
                positional = [
                    p
                    for p in signature.parameters.values()
                    if not p.kind & inspect.Parameter.VAR_POSITIONAL
                ]
                self._accepts_event = len(positional) >= 3

    @property
    def effects(self) -> Effects:
        """The produce-scoped effect slot (authoring surface, §24).

        Only meaningful *inside* `produce()`: the runtime pushes a fresh slot
        per execution. Returns an error outside a run.
        """
        from .effects import current_effects

        slot = current_effects()
        if slot is None:
            raise RuntimeError(
                "Produce.effects is only available while the runtime executes "
                "this produce — write effects inside produce(), not before it."
            )
        return slot

    async def produce(
        self,
        context: Context,
        inputs: list[Artifact[Any]],
        event: Event | None = None,
    ) -> None:
        """Runs the factory and writes its effect into the slot (§24).

        Subclass-style overrides write `self.effects.*` and return None;
        a `None` return means "no work". (The progress nest the old
        `Patch | None` return — the runtime compiles the slot now.)
        """
        if self.factory is None:
            return None

        if self._accepts_event:
            result = self.factory(context, inputs, event)
        else:
            result = self.factory(context, inputs)
        if asyncio.iscoroutine(result):
            result = await result

        self._apply_result(result)

    def _apply_result(self, result: Any) -> None:
        """Writes a factory result into the effect slot (§24).

        `None` — nothing; a model or a list of models — creates; a Patch — the
        factory-level legacy escape (its operations are appended to the effects).
        """
        if result is None:
            return
        if isinstance(result, Patch):
            for op in result.operations:
                self.effects.add(op)
            return
        if isinstance(result, list):
            for item in result:
                self.effects.create(item)
        else:
            self.effects.create(result)


def produce(
    artifact_type: ArtifactType,
) -> Callable[[Callable[..., Any]], Produce[Any]]:
    """Decorator to create a Produce from a function.

    The function must accept (context, inputs, event) and return a model,
    a list of models, a Patch, or None; the produce writes its effects and its
    `produce` returns None (the runtime compiles the slot).
    """

    def decorator(func: Callable[..., Any]) -> Produce[Any]:
        # Check the signature
        sig = inspect.signature(func)
        params = list(sig.parameters.values())
        # Expect three parameters: context, inputs, event
        if len(params) != 3:
            raise TypeError(
                f"Function {func.__name__} must accept exactly 3 arguments: (context, inputs, event)"
            )

        class _FunctionProduce(Produce[Any]):
            async def produce(
                self,
                context: Context,
                inputs: list[Artifact[Any]],
                event: Event | None = None,
            ) -> None:
                result = func(context, inputs, event)
                if asyncio.iscoroutine(result):
                    result = await result
                self._apply_result(result)

        # Return an instance of the Produce class with the required artifact_type
        instance = _FunctionProduce(artifact_type=artifact_type)
        return instance

    return decorator
