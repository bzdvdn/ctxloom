from __future__ import annotations

import copy
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, TypeVar, cast, overload

from pydantic import BaseModel

from .artifacts import Artifact
from .checkpoints import CheckpointBackend, FileBackend
from .commit import Commit
from .events import Event, EventType
from .interrupt import PendingQuestion
from .patches import (
    Create,
    Delete,
    Link,
    Operation,
    Relation,
    Unlink,
    Update,
)
from .resources import RuntimeResources
from .streaming import EventHub, ProgressEvent, QueueEvent

TData = TypeVar("TData", bound=BaseModel)
TArtifact = TypeVar("TArtifact", bound=BaseModel)


@dataclass
class View:
    """Context projection for an agent: artifact references + serialization (§27).

    Used for building the prompt and controlling the token budget (§58):
    `tokens_estimate` is a rough estimate (≈4 characters per token).
    """

    artifacts: list[Artifact[Any]] = field(default_factory=list)

    def render(self, *, max_chars: int | None = None) -> str:
        """Serializes artifacts into compact text for the prompt.

        Each artifact is a line `[Type] {json}`. `max_chars` truncates the result.
        """
        lines = [
            f"[{type(a.data).__name__}] "
            + json.dumps(a.data.model_dump(mode="json"), ensure_ascii=False)
            for a in self.artifacts
        ]
        text = "\n".join(lines)
        if max_chars is not None and len(text) > max_chars:
            return text[:max_chars]
        return text

    @property
    def tokens_estimate(self) -> int:
        """Rough estimate of the prompt size in tokens (≈4 chars/token, §58)."""
        return max(1, len(self.render()) // 4)


class Context:
    """Central artifact store with an event queue.

    Git-like model: every applied commit forms a new Context version (head).
    Commits chain through parent_id and carry a reads/writes trace — the actual
    agent linkage via consumes/produces.
    """

    def __init__(self, resources: RuntimeResources | None = None):
        self._artifacts: dict[str, Artifact[Any]] = {}
        self._events: list[Event] = []
        self._commits: list[Commit] = []
        self._version: int = 0
        self._head_id: str | None = None
        self.resources = resources or RuntimeResources()
        self._hub = EventHub()
        self._relations: dict[tuple[str, str, str], Relation] = {}

    # ---- announce: agent progress events streamed out ----

    def announce(self, message: str, *, kind: str = "status", **data: Any) -> None:
        """Publishes a progress event to active streams (no-op without subscribers).

        `kind` is a category for the application: "status" (domain agent statuses),
        "agent" (internal, from framework producers like ToolUse).
        The application itself decides which kinds to show the user.
        """
        if self._hub.has_subscribers:
            self._hub.publish(
                ProgressEvent(
                    kind=kind,
                    message=message,
                    data=data,
                )
            )

    def subscribe(self) -> QueueEvent:
        return self._hub.subscribe()

    def unsubscribe(self, queue: QueueEvent) -> None:
        self._hub.unsubscribe(queue)

    def create(self, data: TData, id: str | None = None) -> Artifact[TData]:
        """Creates a new artifact and generates an ARTIFACT_CREATED event.

        If a stable id is given and an artifact with it already exists, returns
        the existing one without creating a duplicate or an event (idempotency, §42).
        """
        if id is not None and id in self._artifacts:
            return self._artifacts[id]
        artifact = Artifact(data=data, id=id)
        self._artifacts[artifact.id] = artifact
        self._events.append(
            Event(
                type=EventType.ARTIFACT_CREATED,
                artifact_type=type(data),
                artifact_id=artifact.id,
            )
        )
        return artifact

    def get(self, artifact_id: str) -> Artifact[Any] | None:
        """Returns the artifact by id or None."""
        return self._artifacts.get(artifact_id)

    def update(self, artifact_id: str, new_data: TData) -> Artifact[TData] | None:
        """Updates artifact data, creates a new version, generates ARTIFACT_UPDATED.

        If the data did not change, the version and the event are left untouched:
        no-op patches must not cascade into reactions (§41, §42).
        """
        artifact = self._artifacts.get(artifact_id)
        if artifact is None:
            return None
        if artifact.data == new_data:
            return artifact
        artifact.update(new_data)
        self._events.append(
            Event(
                type=EventType.ARTIFACT_UPDATED,
                artifact_type=type(new_data),
                artifact_id=artifact.id,
            )
        )
        return artifact

    def delete(self, artifact_id: str) -> bool:
        """Deletes the artifact and generates ARTIFACT_DELETED."""
        artifact = self._artifacts.pop(artifact_id, None)
        if artifact is None:
            return False
        self._events.append(
            Event(
                type=EventType.ARTIFACT_DELETED,
                artifact_type=type(artifact.data),
                artifact_id=artifact.id,
            )
        )
        return True

    @overload
    def list_artifacts(self, artifact_type: None = None) -> list[Artifact[Any]]: ...

    @overload
    def list_artifacts(
        self, artifact_type: type[TArtifact]
    ) -> list[Artifact[TArtifact]]: ...

    def list_artifacts(
        self, artifact_type: type[TArtifact] | None = None
    ) -> list[Artifact[Any]]:
        """Returns a list of artifacts, optionally filtered by data type."""
        if artifact_type is None:
            return list(self._artifacts.values())
        return [
            cast(Artifact[TArtifact], a)
            for a in self._artifacts.values()
            if isinstance(a.data, artifact_type)
        ]

    # ---- Context Views (§27): projection for the agent/prompt within the budget ----

    def view(
        self,
        artifact_type: type[BaseModel] | tuple[type[BaseModel], ...] | None = None,
        *,
        condition: Callable[[Artifact[Any]], bool] | None = None,
        limit: int | None = None,
    ) -> View:
        """Artifact projection for the agent (§27): by type/condition/limit.

        The View does not copy state — it is references to artifacts plus
        serialization for the prompt. `tokens_estimate` lets the agent stay within
        the token budget (§58): build the view, check the estimate, reduce `limit`
        if needed.
        """
        if artifact_type is None:
            artifacts = list(self._artifacts.values())
        else:
            artifacts = [
                a for a in self._artifacts.values() if isinstance(a.data, artifact_type)
            ]
        if condition is not None:
            artifacts = [a for a in artifacts if condition(a)]
        if limit is not None:
            artifacts = artifacts[:limit]
        return View(artifacts=artifacts)

    # ---- Relations: the artifact graph (§15) ----

    def link(self, source_id: str, relation: str, target_id: str) -> Relation:
        """Establishes a link `source_id —relation→ target_id` (idempotently, §42)."""
        rel = Relation(source_id=source_id, relation=relation, target_id=target_id)
        self._relations[(rel.source_id, rel.relation, rel.target_id)] = rel
        return rel

    def unlink(
        self,
        source_id: str,
        relation: str | None = None,
        target_id: str | None = None,
    ) -> int:
        """Removes links; `relation`/`target_id` = None mean "any"."""
        removed = 0
        for key in [k for k in self._relations if k[0] == source_id]:
            if relation is not None and key[1] != relation:
                continue
            if target_id is not None and key[2] != target_id:
                continue
            del self._relations[key]
            removed += 1
        return removed

    def relations(
        self,
        source_id: str | None = None,
        relation: str | None = None,
        target_id: str | None = None,
    ) -> list[Relation]:
        """All links, optionally filtered by any edge component."""
        result: list[Relation] = []
        for rel in self._relations.values():
            if source_id is not None and rel.source_id != source_id:
                continue
            if relation is not None and rel.relation != relation:
                continue
            if target_id is not None and rel.target_id != target_id:
                continue
            result.append(rel)
        return result

    def incoming(self, target_id: str, relation: str | None = None) -> list[Relation]:
        """Links pointing at `target_id` (for provenance: who references what)."""
        return self.relations(target_id=target_id, relation=relation)

    def related(
        self, source_id: str, relation: str | None = None
    ) -> list[Artifact[Any]]:
        """Target artifacts of outgoing links (existing ones; "dangling" ones are skipped)."""
        targets: list[Artifact[Any]] = []
        seen: set[str] = set()
        for rel in self.relations(source_id=source_id, relation=relation):
            artifact = self._artifacts.get(rel.target_id)
            if artifact is not None and rel.target_id not in seen:
                targets.append(artifact)
                seen.add(rel.target_id)
        return targets

    def dangling_relations(self) -> list[Relation]:
        """Links with a non-existent source or target (§69): the state is visible,
        not hidden in a string."""
        return [
            rel
            for rel in self._relations.values()
            if rel.source_id not in self._artifacts
            or rel.target_id not in self._artifacts
        ]

    # ---- HITL: questions awaiting a human answer ----

    def interrupt(
        self,
        question: str,
        *,
        kind: str = "general",
        notes: dict[str, Any] | None = None,
    ) -> Artifact[PendingQuestion]:
        """Poses a question to a human: creates a PendingQuestion in the context."""
        return self.create(
            PendingQuestion(question=question, kind=kind, notes=notes or {})
        )

    def pending_questions(self) -> list[Artifact[PendingQuestion]]:
        """Unanswered questions awaiting the human."""
        return [a for a in self.list_artifacts(PendingQuestion) if not a.data.answered]

    def has_pending_question(self) -> bool:
        return bool(self.pending_questions())

    def latest_pending_question(self) -> Artifact[PendingQuestion] | None:
        questions = self.pending_questions()
        if not questions:
            return None
        return max(questions, key=lambda a: a.created_at)

    def resume(self, question_id: str, answer: str) -> Artifact[PendingQuestion] | None:
        """A human's answer is a regular patch: marks the question as answered.

        Generates ARTIFACT_UPDATED, which agents subscribed to
        PendingQuestion(answered=True) react to.
        """
        artifact = self._artifacts.get(question_id)
        if artifact is None or not isinstance(artifact.data, PendingQuestion):
            return None
        updated = artifact.data.model_copy(
            update={
                "answered": True,
                "resolution": answer,
                "resolved_at": datetime.now(UTC),
            }
        )
        return self.update(question_id, updated)

    def drain_events(self) -> list[Event]:
        """Drains and clears the event queue."""
        events = self._events
        self._events = []
        return events

    def clone(self) -> Context:
        new_ws = Context()
        for artifact in self._artifacts.values():
            new_artifact = Artifact(
                data=artifact.data.model_copy(deep=True),
                id=artifact.id,  # <-- important!
                created_by_commit=artifact.created_by_commit,
            )
            new_artifact._history = [v.model_copy(deep=True) for v in artifact._history]
            new_artifact.created_at = artifact.created_at
            new_artifact.updated_at = artifact.updated_at
            new_ws._artifacts[artifact.id] = new_artifact
        new_ws._version = self._version
        new_ws._head_id = self._head_id
        new_ws._commits = copy.deepcopy(self._commits)
        new_ws._relations = dict(self._relations)
        return new_ws

    def merge_from(self, other: Context) -> None:
        operations: list[Operation] = []
        for other_id in list(other._artifacts.keys()):
            other_artifact = other._artifacts[other_id]
            if other_id in self._artifacts:
                current = self._artifacts[other_id]
                if other_artifact.version > current.version:
                    new_data = other_artifact.data.model_copy(deep=True)
                    self.update(other_id, new_data)
                    operations.append(Update(other_id, new_data))
            else:
                new_data = other_artifact.data.model_copy(deep=True)
                self.create(new_data)
                operations.append(Create(new_data))
        for rel in other.relations():
            if (rel.source_id, rel.relation, rel.target_id) not in self._relations:
                self.link(rel.source_id, rel.relation, rel.target_id)
                operations.append(Link(rel.source_id, rel.relation, rel.target_id))
        if operations:
            self.log_commit(
                Commit(author="merge", message="Merged Context", operations=operations)
            )

    def log_commit(self, commit: Commit) -> None:
        """Applies the commit to the repository: fills in parent/version, moves head."""
        commit.parent_id = self._head_id
        commit.context_version = self._version + 1
        self._commits.append(commit)
        self._head_id = commit.id
        self._version += 1

    def commit_log(self) -> list[Commit]:
        return list(self._commits)

    @property
    def version(self) -> int:
        """Current Context version (number of applied commits)."""
        return self._version

    @property
    def head_id(self) -> str | None:
        """Id of the last commit (HEAD)."""
        return self._head_id

    def history(self) -> list[Commit]:
        """History: an ordered chain of commits from the oldest to head."""
        return list(self._commits)

    def _replay_state(self, upto_version: int) -> dict[str, Any]:
        """Replays the artifact state by applying commits up to and including the version."""
        state: dict[str, Any] = {}
        for commit in self._commits[:upto_version]:
            for op in commit.operations:
                if isinstance(op, Create) and op.artifact_id is not None:
                    state[op.artifact_id] = op.data.model_copy(deep=True)
                elif isinstance(op, Update):
                    state[op.artifact_id] = op.new_data.model_copy(deep=True)
                elif isinstance(op, Delete):
                    state.pop(op.artifact_id, None)
        return state

    def _replay_relations(
        self, upto_version: int
    ) -> dict[tuple[str, str, str], Relation]:
        """Replays the link graph from commits up to and including the version."""
        relations: dict[tuple[str, str, str], Relation] = {}
        for commit in self._commits[:upto_version]:
            for op in commit.operations:
                if isinstance(op, Link):
                    key = (op.artifact_id, op.relation, op.target_id)
                    relations[key] = Relation(*key)
                elif isinstance(op, Unlink):
                    for key in list(relations.keys()):
                        if key[0] != op.artifact_id:
                            continue
                        if op.relation is not None and key[1] != op.relation:
                            continue
                        if op.target_id is not None and key[2] != op.target_id:
                            continue
                        del relations[key]
        return relations

    def diff(self, version_a: int, version_b: int) -> dict[str, Any]:
        """State delta between two Context versions.

        Returns {"added": {id: data}, "removed": {id: data}, "changed": {id: {old, new}}}.
        The diff compares the versioned state (commits); artifacts created directly
        outside commits (the "working tree") do not participate.
        """
        if not (0 <= version_a <= version_b <= self._version):
            raise ValueError(
                f"Invalid versions: {version_a}..{version_b} (head={self._version})"
            )
        snap_a = self._replay_state(version_a)
        snap_b = self._replay_state(version_b)
        result: dict[str, Any] = {"added": {}, "removed": {}, "changed": {}}
        for aid in snap_b.keys() - snap_a.keys():
            result["added"][aid] = snap_b[aid].model_dump()
        for aid in snap_a.keys() - snap_b.keys():
            result["removed"][aid] = snap_a[aid].model_dump()
        for aid in snap_a.keys() & snap_b.keys():
            if snap_a[aid] != snap_b[aid]:
                result["changed"][aid] = {
                    "old": snap_a[aid].model_dump(),
                    "new": snap_b[aid].model_dump(),
                }
        return result

    def snapshot(self) -> dict[str, Any]:
        """Consistent snapshot of the current artifact state (id → data)."""
        return {aid: art.data.model_dump() for aid, art in self._artifacts.items()}

    # ---- Invalidation / staleness (§43–44) based on recorded reads ----

    def _producing_commit(self, artifact_id: str) -> Commit | None:
        """The last commit that wrote the artifact (create or update)."""
        for commit in reversed(self._commits):
            for write in commit.writes:
                if write.artifact_id == artifact_id:
                    return commit
        return None

    def stale_artifacts(self) -> list[Artifact[Any]]:
        """Artifacts whose parents (reads in the producing commit) are now newer versions.

        Dependencies are built from the actual reads recorded by the runtime via
        consumes — a link derived from execution, not an author-drawn graph.
        """
        stale: list[Artifact[Any]] = []
        for artifact_id, artifact in self._artifacts.items():
            commit = self._producing_commit(artifact_id)
            if commit is None:
                continue
            for read in commit.reads:
                current = self._artifacts.get(read.artifact_id)
                if current is not None and current.version > read.version:
                    stale.append(artifact)
                    break
        return stale

    def has_stale(self) -> bool:
        return bool(self.stale_artifacts())

    def _rebuild_artifacts_from_commits(
        self, upto_version: int
    ) -> dict[str, Artifact[Any]]:
        state = self._replay_state(upto_version)
        return {aid: Artifact(data=data, id=aid) for aid, data in state.items()}

    def checkout(self, version: int) -> None:
        """Moves head back to a previous version (rollback along the commit chain).

        Artifacts not part of the versioned history (created directly outside
        commits — the "working tree") are preserved.
        """
        if not (0 <= version <= self._version):
            raise ValueError(
                f"Invalid checkout version: {version} (head={self._version})"
            )
        touched: set[str] = set()
        for commit in self._commits[version:]:
            for op in commit.operations:
                if isinstance(op, (Create, Update, Delete)) and op.artifact_id:
                    touched.add(op.artifact_id)
        rebuilt = self._rebuild_artifacts_from_commits(version)
        for aid, art in self._artifacts.items():
            if aid not in touched:
                rebuilt[aid] = art
        self._artifacts = rebuilt

        # Relations: those committed up to `version` plus the "working tree"
        # (created directly outside commits) are kept, as with artifacts. Links
        # introduced by commits in the [version:] range are rolled back.
        committed_now = self._replay_relations(self._version)
        working_tree_rels = {
            key: rel for key, rel in self._relations.items() if key not in committed_now
        }
        self._relations = {**self._replay_relations(version), **working_tree_rels}

        self._events = []
        if version == 0:
            self._head_id = None
        else:
            self._head_id = self._commits[version - 1].id
        del self._commits[version:]
        self._version = version

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self._version,
            "head_id": self._head_id,
            "artifacts": {aid: art.to_dict() for aid, art in self._artifacts.items()},
            "relations": [rel.to_dict() for rel in self._relations.values()],
            "commits": [c.to_dict() for c in self._commits],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Context:
        ws = cls()
        for aid, art_dict in d["artifacts"].items():
            artifact = Artifact.from_dict(art_dict)
            ws._artifacts[aid] = artifact
        for rel_dict in d.get("relations", []):
            rel = Relation.from_dict(rel_dict)
            ws._relations[(rel.source_id, rel.relation, rel.target_id)] = rel
        ws._commits = [Commit.from_dict(cd) for cd in d["commits"]]
        ws._version = d.get("version", 0)
        if ws._version is None:
            ws._version = len(ws._commits)
        ws._head_id = d.get("head_id")
        if ws._head_id is None and ws._commits:
            ws._head_id = ws._commits[-1].id
        return ws

    def save_checkpoint(self, backend_or_path: str | CheckpointBackend) -> None:
        backend: CheckpointBackend
        if isinstance(backend_or_path, str):
            backend = FileBackend(backend_or_path)
        else:
            backend = backend_or_path
        backend.save(self.to_dict())

    @classmethod
    def load_checkpoint(cls, backend_or_path: str | CheckpointBackend) -> Context:
        backend: CheckpointBackend
        if isinstance(backend_or_path, str):
            backend = FileBackend(backend_or_path)
        else:
            backend = backend_or_path
        data = backend.load()
        return cls.from_dict(data)

    def __repr__(self) -> str:
        return f"<Context artifacts={len(self._artifacts)} pending_events={len(self._events)}>"
