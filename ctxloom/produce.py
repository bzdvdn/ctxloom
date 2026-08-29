from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable
from typing import Any, Generic, TypeVar

from pydantic import BaseModel

from .artifacts import Artifact, ArtifactType
from .context import Context
from .events import Event
from .patches import Patch

TOut = TypeVar("TOut", bound=BaseModel)


class Produce(Generic[TOut]):
    """Describes the produced artifact type and how it is created.

    You can subclass and override `produce`, or pass a factory.
    The factory may return:
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

    async def produce(
        self,
        context: Context,
        inputs: list[Artifact[Any]],
        event: Event | None = None,
    ) -> Patch | None:
        """Creates a Patch from the inputs (and, optionally, the trigger event).

        Overrides (subclass-style) must annotate `event: Event | None`
        and return `Patch | None`; None — "no work".
        """
        if self.factory is None:
            return Patch()

        if self._accepts_event:
            result = self.factory(context, inputs, event)
        else:
            result = self.factory(context, inputs)
        if asyncio.iscoroutine(result):
            result = await result

        if result is None:
            return Patch()

        if isinstance(result, Patch):
            return result

        patch = Patch()
        if isinstance(result, list):
            for item in result:
                patch.create(item)
        else:
            patch.create(result)
        return patch


def produce(
    artifact_type: ArtifactType,
) -> Callable[[Callable[..., Any]], Produce[Any]]:
    """Decorator to create a Produce from a function.

    The function must accept (context, inputs, event) and return a Patch,
    a list of models, a single model, or None.
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
            ) -> Patch:
                result = func(context, inputs, event)
                if asyncio.iscoroutine(result):
                    result = await result
                if result is None:
                    return Patch()
                if isinstance(result, Patch):
                    return result
                patch = Patch()
                if isinstance(result, list):
                    for item in result:
                        patch.create(item)
                else:
                    patch.create(result)
                return patch

        # Return an instance of the Produce class with the required artifact_type
        instance = _FunctionProduce(artifact_type=artifact_type)
        return instance

    return decorator
