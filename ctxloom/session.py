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

    def save(self) -> None:
        self._store.save_session(self.session_id, self.context)

    def delete(self) -> None:
        self._store.delete_session(self.session_id)


class SessionStore:
    """Session store on top of KVBackend (session_id → Context)."""

    def __init__(self, backend: KVBackend):
        self.backend = backend

    def save_session(self, session_id: str, context: Context) -> None:
        self.backend.set(session_id, context.to_dict())

    def load_session(
        self,
        session_id: str,
        resources: RuntimeResources | None = None,
    ) -> Context | None:
        data = self.backend.get(session_id)
        if data is None:
            return None
        context = Context.from_dict(data)
        context.resources = resources or RuntimeResources()
        return context

    def has_session(self, session_id: str) -> bool:
        return self.backend.get(session_id) is not None

    def list_sessions(self) -> list[str]:
        return self.backend.keys()

    def delete_session(self, session_id: str) -> None:
        self.backend.delete(session_id)

    def open(
        self,
        session_id: str,
        resources: RuntimeResources | None = None,
    ) -> Session:
        """Opens a session: loads an existing one or creates an empty one."""
        context = self.load_session(session_id, resources)
        loaded = context is not None
        if context is None:
            context = Context(resources=resources or RuntimeResources())
        return Session(session_id, context, self, loaded=loaded)
