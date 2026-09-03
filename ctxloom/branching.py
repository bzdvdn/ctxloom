"""ctxloom.branching — durable forks on top of a KV backend (§39-§40).

`Context.branch()`/`Context.merge()` (in `ctxloom.context`) provide the state
semantics; this module only *persists* named forks so they survive a restart:

    store = BranchStore(SQLiteKVBackend("sessions.sqlite3"))
    await store.save_branch(ctx_branch, session_id="demo", name="hypothesis-a")
    restored = await store.load_branch("demo", "hypothesis-a")

Each branch key holds the full self-contained context (`to_dict`, which now also
carries the fork base snapshot), so a merged restart keeps `merge()` conflict
detection working. Naming follows `branch:<session>:<name>`; the KV backend stays
the only storage primitive — branches are a convention on top of it, not a new
backend (matching the constitution: semantics live in Context operations).
"""

from __future__ import annotations

from .checkpoints import KVBackend
from .context import Context


class BranchStore:
    """Persists named branches (`branch:<session>:<name>`) over a KV backend."""

    def __init__(self, backend: KVBackend):
        self.backend = backend

    @staticmethod
    def _key(session_id: str, name: str) -> str:
        return f"branch:{session_id}:{name}"

    async def save_branch(self, context: Context, *, session_id: str, name: str) -> None:
        """Saves a branch (including its fork base snapshot, §40)."""
        await context.to_kv(self.backend, self._key(session_id, name))

    async def load_branch(self, session_id: str, name: str) -> Context | None:
        """Loads a branch, or None if it does not exist."""
        return await Context.from_kv(self.backend, self._key(session_id, name))

    async def list_branches(self, session_id: str) -> list[str]:
        prefix = f"branch:{session_id}:"
        names: list[str] = []
        all_keys = await self.backend.keys()
        for key in all_keys:
            if key.startswith(prefix):
                names.append(key[len(prefix) :])
        return sorted(names)

    async def delete_branch(self, session_id: str, name: str) -> None:
        await self.backend.delete(self._key(session_id, name))


__all__ = ["BranchStore"]
