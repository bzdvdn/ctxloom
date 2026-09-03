"""ctxloom.produce — how a produce writes an artifact (§24).

Two styles cover almost everything and are the ones this repo's examples use:

- **Subclass + effects** — `class X(Produce[Model]): async def produce(self,
  context, inputs, event=None): self.effects.create(...); return None`. Use
  this whenever the produce has its own state-free logic worth naming as a
  class (the common case in every example under `examples/`).
- **`@produce(Model)` function with `effects`** — `@produce(Model)\\ndef f(context,
  inputs, effects): effects.create(...)`. Same effects-first shape, no class
  ceremony — pick this for a short, one-off produce.

Everything else `Produce`/`produce()` also accept — a plain return-style
`@produce` function (return a model / list / `Patch` / `None` instead of
writing `effects`), or a two-argument `factory=` callable passed to the
`Produce()` constructor — still works and is still tested
(`tests/test_produce_styles.py`), kept for existing code and advanced cases
(e.g. wrapping a function that predates `effects`). New code should reach for
one of the two styles above first.
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable
from typing import Any, Generic, TypeVar, get_args, get_origin

from pydantic import BaseModel

from .artifacts import Artifact, ArtifactType
from .context import Context
from .effects import Effects
from .events import Event
from .patches import Patch

TOut = TypeVar("TOut", bound=BaseModel)


class Produce(Generic[TOut]):
    """Describes the produced artifact type and how it is created.

    `artifact_type` is auto-derived from the generic when a subclass is written
    as `class X(Produce[Foo])` — write it explicitly only to override or when
    the class has no generic (e.g. programmatic `Produce(Foo)`).
    """

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if "artifact_type" in cls.__dict__ or cls.artifact_type is not None:
            return
        for base in getattr(cls, "__orig_bases__", ()):
            if get_origin(base) is Produce:
                args = get_args(base)
                if args and isinstance(args[0], type):
                    cls.artifact_type = args[0]
                    return

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

    The function must accept ``(context, inputs)`` plus, optionally, ``event``
    and/or ``effects`` (each recognized by name):

    - ``def f(context, inputs)`` — return style (no event, no slot);
    - ``def f(context, inputs, event)`` — return style with the event;
    - ``def f(context, inputs, effects)`` — author the produce-scoped
      ``Effects`` slot directly (the same surface as ``self.effects``);
    - ``def f(context, inputs, event, effects)`` — both.

    Return style: return a model / a list of models / a ``Patch`` / ``None``;
    the runtime writes them into the slot (reate/append) as usual. Effects
    style: write ``effects.create/update/link/ask/...`` and return ``None`` —
    the function behaves exactly like a class produce with ``self.effects``.
    """

    def decorator(func: Callable[..., Any]) -> Produce[Any]:
        # Recognize which optional parameters the function declares.
        params = list(inspect.signature(func).parameters.values())
        names = [p.name for p in params]
        if len(params) < 2:
            raise TypeError(
                f"Function {func.__name__} must accept at least (context, inputs)"
            )
        accepts_event = "event" in names
        accepts_effects = "effects" in names

        class _FunctionProduce(Produce[Any]):
            async def produce(
                self,
                context: Context,
                inputs: list[Artifact[Any]],
                event: Event | None = None,
            ) -> None:
                args: list[Any] = [context, inputs]
                if accepts_event:
                    args.append(event)
                result = (
                    func(*args, effects=self.effects)
                    if accepts_effects
                    else func(*args)
                )
                if asyncio.iscoroutine(result):
                    result = await result
                self._apply_result(result)

        # Return an instance of the Produce class with the required artifact_type
        instance = _FunctionProduce(artifact_type=artifact_type)
        return instance

    return decorator
