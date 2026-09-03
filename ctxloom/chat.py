"""ctxloom.chat — the app-facing chat layer (sessions + turns + history).

A thin, transport-agnostic layer on top of the runtime: it owns sessions
(`SessionStore`), the wire-neutral turn loop ("create the user artifact, stream
status events, then the terminal reply") and history reconstruction. It knows
nothing about HTTP/SSE — the web adapter lives in `ctxloom.web`.

Two levels of use:

- `ChatAssistant` — concrete, batteries-included for the canonical chat
  contract. Configure it with hooks (agents, `user_message` model, `reply`).
- `run_message` / `default_session_state` — building blocks, for apps whose
  loop or transport differs (bots, custom SSE, medic-lab-style steering).
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Callable, Sequence
from typing import Any

from pydantic import BaseModel

from .agents import Agent
from .budget import Budget
from .context import Context
from .resources import RuntimeResources
from .runtime import Runtime
from .session import Session, SessionStore

logger = logging.getLogger("ctxloom.chat")


class ChatEvent(BaseModel):
    """One frame of a chat turn, transport-neutral.

    `kind` is the wire contract of the canonical chat:
    ``session`` (start), ``status`` (progress announcement) or ``message``
    (terminal reply).
    """

    kind: str
    session_id: str = ""
    message: str = ""
    waiting: bool = False
    payload: dict[str, Any] = {}


# --- building blocks ------------------------------------------------------- #


def _fallback_payload(fallback_reply: str) -> dict[str, Any]:
    """The honest terminal payload when a turn crashed (§59)."""
    return {"reply": fallback_reply, "waiting": False, "error": True}


async def run_message(
    runtime: Runtime,
    text: str,
    *,
    user_message: type[BaseModel],
    reply: Callable[[Context, str], dict[str, Any]],
    session_id: str = "",
    create_message: Callable[[Context, str], str] | None = None,
    status_kinds: Sequence[str] = ("status",),
    fallback_reply: str = "No reply assembled.",
) -> AsyncIterator[ChatEvent]:
    """Run one user turn: create the input artifact, stream status events,
    emit the terminal reply.

    `reply(ctx, msg_id) -> dict` adapts the app's state into the `message`
    payload (the only domain hook). Statuses are deduplicated so repeated
    progress announcements don't double-emit.

    `create_message(ctx, text) -> msg_id` overrides how the turn enters the
    context (default: create a `user_message` artifact) — HITL apps where a
    new turn resumes a pending question instead of appending a message
    (devops-style clarify) pass their own.

    `status_kinds` selects which progress event kinds are forwarded as `status`
    frames (default: only `status`; e.g. tool-announcing demos also forward
    `agent`).

    Errors never escape: a failed runtime/reply degrades to the `fallback_reply`
    `message` event (logged via `ctxloom.chat` logger) so a web layer never
    delivers a 500 mid-stream.
    """
    forwarded = set(status_kinds)
    ctx = runtime.context
    try:
        if create_message is not None:
            msg_id = create_message(ctx, text)
        else:
            msg_id = ctx.create(user_message(text=text, session_id=session_id)).id
    except Exception:
        logger.exception("chat.run_message: failed to enter the turn")
        yield ChatEvent(
            kind="message",
            session_id=session_id,
            payload=_fallback_payload(fallback_reply),
        )
        return

    last: str | None = None
    try:
        async for event in runtime.astream():
            if event.kind not in forwarded:
                continue
            if event.message == last:
                continue
            last = event.message
            yield ChatEvent(kind="status", session_id=session_id, message=event.message)
    except Exception:
        # The runtime crashed — the context may be half-applied. Skip the reply
        # hook (it could echo stale state) and degregate to the honest fallback.
        logger.exception("chat.run_message: runtime crashed inside the turn")
        yield ChatEvent(
            kind="message",
            session_id=session_id,
            payload=_fallback_payload(fallback_reply),
        )
        return
    try:
        payload = reply(ctx, msg_id)
    except Exception:
        logger.exception("chat.run_message: reply hook crashed")
        payload = _fallback_payload(fallback_reply)
    yield ChatEvent(
        kind="message",
        session_id=session_id,
        payload=payload or _fallback_payload(fallback_reply),
    )


def default_session_state(
    ctx: Context, *, user_message: type[BaseModel]
) -> dict[str, Any]:
    """Generic history: every artifact with a `text` field, in creation order.

    Artifacts of `user_message`'s type are marked `user`, everything else —
    `assistant`. Apps with richer reply payloads pass their own hook.
    """
    messages: list[dict[str, Any]] = []
    for artifact in sorted(ctx.list_artifacts(), key=lambda a: a.created_at):
        data = artifact.data
        text = getattr(data, "text", None)
        if not isinstance(text, str):
            continue
        role = "user" if isinstance(data, user_message) else "assistant"
        messages.append(
            {
                "role": role,
                "text": text,
                "at": artifact.created_at.isoformat(),
            }
        )
    return {"messages": messages}


def _resolve(value: Any) -> Any:
    return value() if callable(value) else value


# --- the canonical chat assistant ----------------------------------------- #


class ChatAssistant:
    """Session-persisted chat over the runtime, for the canonical contract.

    Configure with hooks — the assistant owns sessions, the turn loop and
    history. `agents`/`resources` accept values or callables (resolved per
    request, so a fresh `RuntimeResources` can replace providers).

    A callable `resources=` is assumed to build a fresh, turn-scoped
    `RuntimeResources` each call (e.g. `resources=lambda: build_resources()`)
    — `stream()` closes it (`RuntimeResources.aclose()`) after every turn, so
    its provider's HTTP client doesn't leak. Pass a plain `RuntimeResources`
    instance instead when you want one shared, long-lived provider across
    turns/sessions — that instance is never closed automatically; close it
    yourself at real shutdown.

    Base usage:

        assistant = ChatAssistant(
            store=store,
            agents=ALL_AGENTS,
            user_message=UserQuery,
            reply=knowledge_reply,
            resources=lambda: build_resources(),
        )
        async for ev in assistant.stream("hello", session_id="s1"):
            ...
    """

    def __init__(
        self,
        *,
        store: SessionStore,
        agents: Sequence[Agent] | Callable[[], Sequence[Agent]],
        user_message: type[BaseModel],
        reply: Callable[[Context, str], dict[str, Any]],
        session_state: Callable[[Context], dict[str, Any]] | None = None,
        resources: RuntimeResources | Callable[[], RuntimeResources] | None = None,
        budget: Budget | None = None,
        max_concurrency: int | None = None,
        tracer: Any = None,
        create_message: Callable[[Context, str], str] | None = None,
        status_kinds: Sequence[str] = ("status",),
        fallback_reply: str = "No reply assembled.",
    ):
        self.store = store
        self._agents = agents
        self._user_message = user_message
        self._reply = reply
        self._session_state = session_state
        self._resources = resources
        self._budget = budget
        self._max_concurrency = max_concurrency
        self._tracer = tracer
        self._create_message = create_message
        self._status_kinds = tuple(status_kinds)
        self._fallback_reply = fallback_reply

    async def _open(self, session_id: str) -> Session:
        return await self.store.open(session_id, resources=_resolve(self._resources))

    def _build_runtime(self, session: Session) -> Runtime:
        return Runtime(
            session.context,
            agents=list(_resolve(self._agents)),
            session=session,
            budget=self._budget,
            max_concurrency=self._max_concurrency,
            tracer=_resolve(self._tracer),
        )

    async def stream(self, text: str, session_id: str = "") -> AsyncIterator[ChatEvent]:
        """Stream one turn: ``session`` → ``status``… → ``message``.

        Never raises for app-level failures: session open / runtime crash /
        reply hook all degrade to the fallback `message` and are logged via the
        `ctxloom.chat` logger, so a web layer never delivers a 500 mid-stream.
        """
        try:
            session = await self._open(session_id)
            runtime = self._build_runtime(session)
        except Exception:
            logger.exception(
                "chat.ChatAssistant: failed to open session %r", session_id
            )
            yield ChatEvent(
                kind="message",
                session_id=session_id,
                payload=_fallback_payload(self._fallback_reply),
            )
            return
        yield ChatEvent(kind="session", session_id=session_id)
        try:
            async for event in run_message(
                runtime,
                text,
                user_message=self._user_message,
                reply=self._reply,
                create_message=self._create_message,
                status_kinds=self._status_kinds,
                fallback_reply=self._fallback_reply,
                session_id=session_id,
            ):
                yield event
        finally:
            try:
                await session.save()  # persist the conversation after the turn
            except Exception:
                logger.exception(
                    "chat.ChatAssistant: failed to save session %r", session_id
                )
            if callable(self._resources):
                # A callable `resources=` builds a fresh RuntimeResources (and
                # typically a fresh provider + HTTP client) on every turn —
                # nothing else will ever reference this instance again, so
                # it's this turn's job to close it. A shared instance passed
                # directly is not touched here: it must outlive this turn.
                try:
                    await session.context.resources.aclose()
                except Exception:
                    logger.exception(
                        "chat.ChatAssistant: failed to close per-turn resources %r",
                        session_id,
                    )

    async def invoke(self, text: str, session_id: str = "") -> dict[str, Any]:
        """Run one turn and return the terminal reply (aggregated stream)."""
        message: dict[str, Any] = {}
        async for event in self.stream(text, session_id=session_id):
            if event.kind == "message":
                message = dict(event.payload) or {"reply": self._fallback_reply}
        return message

    async def history(self, session_id: str = "") -> dict[str, Any]:
        """Reconstruct the chat thread of a persisted session."""
        try:
            session = await self._open(session_id)
        except Exception:
            logger.exception("chat.ChatAssistant: history open failed %r", session_id)
            return {"messages": []}
        if not session.loaded:
            return {"messages": []}
        if self._session_state is not None:
            return self._session_state(session.context)
        return default_session_state(session.context, user_message=self._user_message)

    def reply_fallback(self) -> dict[str, Any]:
        """The honest terminal payload when nothing was assembled (§59)."""
        return {"reply": self._fallback_reply, "waiting": False}


__all__ = [
    "ChatAssistant",
    "ChatEvent",
    "default_session_state",
    "run_message",
]
