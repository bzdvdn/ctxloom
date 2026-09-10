from __future__ import annotations

from .checkpoints import KVBackend
from .context import Context
from .resources import RuntimeResources


class Session:
    """Named session: an isolated Context bound to a key-value store.

    Saves the full state (commit chain + working tree + head),
    so after a restart the session resumes from the last commit.
    """

    def __init__(
        self,
        session_id: str,
        context: Context,
        store: SessionStore,
        loaded: bool,
    ):
        self.session_id = session_id
        self.context = context
        self._store = store
        self.loaded = loaded

    async def save(self) -> None:
        await self._store.save_session(self.session_id, self.context)

    async def delete(self) -> None:
        await self._store.delete_session(self.session_id)


class SessionStore:
    """Session store on top of KVBackend (session_id → Context)."""

    def __init__(self, backend: KVBackend):
        self.backend = backend

    async def save_session(self, session_id: str, context: Context) -> None:
        await context.to_kv(self.backend, session_id)

    async def load_session(
        self,
        session_id: str,
        resources: RuntimeResources | None = None,
    ) -> Context | None:
        context = await Context.from_kv(self.backend, session_id)
        if context is None:
            return None
        context.resources = resources or RuntimeResources()
        return context

    async def has_session(self, session_id: str) -> bool:
        return await self.backend.get(session_id) is not None

    async def list_sessions(self) -> list[str]:
        # Branch keys are the BranchStore's namespace — keep them out of sessions.
        keys = await self.backend.keys()
        return [key for key in keys if not key.startswith("branch:")]

    async def delete_session(self, session_id: str) -> None:
        await self.backend.delete(session_id)

    async def open(
        self,
        session_id: str,
        resources: RuntimeResources | None = None,
    ) -> Session:
        """Opens a session: loads an existing one or creates an empty one."""
        context = await self.load_session(session_id, resources)
        loaded = context is not None
        if context is None:
            context = Context(resources=resources or RuntimeResources())
        return Session(session_id, context, self, loaded=loaded)
