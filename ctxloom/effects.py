"""ctxloom.effects — the produce-scoped effect set (§24, §41, §67).

The *authoring surface* of a produce. Instead of hand-assembling a `Patch` on
every turn, a produce writes what should change into its effect slot, and the
runtime compiles the slot into one atomic patch (commit + events + trace):

    class Scout(Produce[SourceRef]):
        async def produce(self, context, inputs, event=None) -> None:
            refs = await fan_out_sources(context, query, owner_id=...)
            self.effects.create(SearchDone(...), id=f"scouted:{qid}")
            return None

`Effects` is produce-scoped and concurrency-safe: the runtime pushes a fresh
slot via a contextvar before invoking the produce and pops it afterwards, so
parallel produces never see each other's effects. Nothing is applied until the
runtime commits — atomicity stays structural (§41), no diff/rollback.

Users rarely touch `Patch` in an ordinary produce: `Effects` is the language,
`Patch` is the compiled transport. Advanced assembly (recipes, tool loops) can
still build a `Patch` explicitly and return it — the runtime merges both.
"""

from __future__ import annotations

from contextvars import ContextVar, Token
from typing import TYPE_CHECKING, Any

from .patches import (
    Create,
    Link,
    Operation,
    Patch,
    Unlink,
    Update,
    _auto_id,
    _id_of,
)

if TYPE_CHECKING:
    from .artifacts import Artifact
    from .context import Context


class Handle:
    """A patch-local handle for a *planned* artifact — link/unlink without ids (§38).

    Returned by `Effects.create`; the id is pinned, so the handle is a valid
    link target (`answer.link("supported_by", evidence)`), and the reader sees
    which artifact a provenance edge comes from.
    """

    __slots__ = ("_effects", "id", "_data")

    def __init__(self, effects: Effects, artifact_id: str, data: Any):
        self._effects = effects
        self.id = artifact_id
        self._data = data

    def link(self, relation: str, target: Any) -> Handle:
        """Appends `Link` from this planned artifact to `target` (id/Artifact/Handle)."""
        self._effects.link(self.id, relation, _id_of(target))
        return self

    def unlink(self, relation: str | None = None, target: Any | None = None) -> Handle:
        self._effects.unlink(
            self.id, relation, _id_of(target) if target is not None else None
        )
        return self

    @property
    def type(self) -> str:
        return type(self._data).__name__

    def __repr__(self) -> str:
        return f"Handle(id={self.id!r}, {self.type})"


class Effects:
    """The current produce's effect set (creates/updates/links to commit once)."""

    __slots__ = ("_context", "operations")

    def __init__(self, context: Context):
        self._context = context
        self.operations: list[Operation] = []

    @property
    def context(self) -> Context:
        return self._context

    def add(self, op: Operation) -> Effects:
        self.operations.append(op)
        return self

    def create(self, data: Any, *, id: str | None = None) -> Handle:
        """Plans a new artifact; returns a linkable/updatable handle (§38)."""
        artifact_id = id or _auto_id(type(data).__name__)
        self.operations.append(Create(data, id=artifact_id))
        return Handle(self, artifact_id, data)

    def update(self, artifact: Artifact[Any], **fields: Any) -> Effects:
        """Bumps fields of an *existing* artifact (a new version)."""
        new_data = artifact.data.model_copy(update=fields)
        self.operations.append(Update(artifact.id, new_data))
        return self

    def delete(self, artifact: Any) -> Effects:
        from .patches import Delete

        self.operations.append(Delete(_id_of(artifact)))
        return self

    def link(self, source: Any, relation: str, target: Any) -> Effects:
        self.operations.append(Link(_id_of(source), relation, _id_of(target)))
        return self

    def ask(
        self,
        question: str,
        *,
        kind: str = "general",
        notes: dict[str, Any] | None = None,
    ) -> Handle:
        """Poses a question to a human (HITL, §60): creates a `PendingQuestion`.

        Returns a handle you can link later; the human answer is recorded via
        `effects.resume(question_art, resolution)` (§60).
        """
        from .interrupt import PendingQuestion

        return self.create(
            PendingQuestion(question=question, kind=kind, notes=dict(notes or {}))
        )

    def resume(self, question: Any, resolution: str) -> Effects:
        """Records the human answer on a `PendingQuestion` (HITL, §60)."""
        from datetime import UTC, datetime

        self.update(
            question,
            answered=True,
            resolution=resolution,
            resolved_at=datetime.now(UTC),
        )
        return self

    def unlink(
        self,
        source: Any,
        relation: str | None = None,
        target: Any | None = None,
    ) -> Effects:
        self.operations.append(
            Unlink(
                _id_of(source), relation, _id_of(target) if target is not None else None
            )
        )
        return self

    def is_empty(self) -> bool:
        return len(self.operations) == 0

    def to_patch(self) -> Patch:
        """Compiles the effects into a `Patch` (the runtime's transport)."""
        patch = Patch()
        for op in self.operations:
            patch.add(op)
        return patch


# --------------------------------------------------------------------------- #
# Produce-scoped slot — the runtime pushes/pops a fresh Effects per produce run
# --------------------------------------------------------------------------- #

_ACTIVE: ContextVar[Effects | None] = ContextVar("ctxloom_effects", default=None)


def current_effects() -> Effects | None:
    """The produce-scoped effect slot, or None outside a running produce."""
    return _ACTIVE.get()


def set_effects(effects: Effects | None) -> Token[Any]:
    return _ACTIVE.set(effects)


def reset_effects(token: Token[Any]) -> None:
    _ACTIVE.reset(token)


__all__ = ["Effects", "Handle", "current_effects", "reset_effects", "set_effects"]
