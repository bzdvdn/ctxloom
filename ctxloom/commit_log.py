"""ctxloom.commit_log — the git-like commit chain (§12).

Extracted out of `Context`: `CommitLog` owns the ordered list of applied
`Commit`s, the current version/head, and the pure "replay commits into a
state snapshot" logic (`replay_state`/`replay_relations`) that `checkout`,
`diff`, and staleness detection all build on. It knows nothing about the
live artifact/relation stores — `Context` still owns those and asks the log
to replay itself when it needs a past or reconstructed state.
"""

from __future__ import annotations

import copy
from typing import Any

from .commit import Commit
from .patches import Create, Delete, Link, Relation, Unlink, Update
from .relations import RelationKey


class CommitLog:
    """The applied-commit chain: append, replay, roll back (§12)."""

    __slots__ = ("_commits", "_version", "_head_id")

    def __init__(self) -> None:
        self._commits: list[Commit] = []
        self._version: int = 0
        self._head_id: str | None = None

    @property
    def version(self) -> int:
        """Current version (number of applied commits)."""
        return self._version

    @property
    def head_id(self) -> str | None:
        """Id of the last commit (HEAD)."""
        return self._head_id

    def append(self, commit: Commit) -> None:
        """Fills in parent/version and moves head (was `Context.log_commit`)."""
        commit.parent_id = self._head_id
        commit.context_version = self._version + 1
        self._commits.append(commit)
        self._head_id = commit.id
        self._version += 1

    def history(self) -> list[Commit]:
        """Ordered chain of commits from the oldest to head."""
        return list(self._commits)

    def __len__(self) -> int:
        return len(self._commits)

    def commits_from(self, index: int) -> list[Commit]:
        """Commits at `index` and after (used by `checkout` to find what a
        rollback would undo)."""
        return self._commits[index:]

    def commits_upto(self, upto_version: int) -> list[Commit]:
        """Commits before `upto_version` (used by the replay methods)."""
        return self._commits[:upto_version]

    def producing_commit(self, artifact_id: str) -> Commit | None:
        """The last commit that wrote the artifact (create or update)."""
        for commit in reversed(self._commits):
            for write in commit.writes:
                if write.artifact_id == artifact_id:
                    return commit
        return None

    def truncate(self, version: int) -> None:
        """Rolls the log back to `version`: drops later commits, moves head.

        `version=0` means "before any commit" (no head).
        """
        if version == 0:
            self._head_id = None
        else:
            self._head_id = self._commits[version - 1].id
        del self._commits[version:]
        self._version = version

    def replay_state(self, upto_version: int) -> dict[str, Any]:
        """Replays the artifact state by applying commits up to and including
        the version."""
        state: dict[str, Any] = {}
        for commit in self.commits_upto(upto_version):
            for op in commit.operations:
                if isinstance(op, Create) and op.artifact_id is not None:
                    state[op.artifact_id] = op.data.model_copy(deep=True)
                elif isinstance(op, Update):
                    state[op.artifact_id] = op.new_data.model_copy(deep=True)
                elif isinstance(op, Delete):
                    state.pop(op.artifact_id, None)
        return state

    def replay_relations(self, upto_version: int) -> dict[RelationKey, Relation]:
        """Replays the link graph from commits up to and including the version."""
        relations: dict[RelationKey, Relation] = {}
        for commit in self.commits_upto(upto_version):
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

    def copy(self) -> CommitLog:
        clone = CommitLog()
        clone._commits = copy.deepcopy(self._commits)
        clone._version = self._version
        clone._head_id = self._head_id
        return clone

    def to_dict(self) -> list[dict[str, Any]]:
        return [c.to_dict() for c in self._commits]

    @classmethod
    def from_dict(
        cls,
        commits: list[dict[str, Any]],
        *,
        version: int | None,
        head_id: str | None,
    ) -> CommitLog:
        log = cls()
        log._commits = [Commit.from_dict(cd) for cd in commits]
        log._version = version if version is not None else len(log._commits)
        log._head_id = (
            head_id
            if head_id is not None
            else (log._commits[-1].id if log._commits else None)
        )
        return log


__all__ = ["CommitLog"]
