"""ctxloom.web — web adapter over the chat layer (FastAPI, SSE).

Because every app already owns its FastAPI instance, this module ships an
`APIRouter`, not an app. Mount it wherever:

    from ctxloom import ChatAssistant, SessionStore
    from ctxloom.web import create_chat_router

    app.include_router(create_chat_router(assistant))

The wire contract is the canonical chat (owned by `ctxloom.chat`):
``session`` → ``status``… → ``message`` over Server-Sent Events, plus the
standard runs (list) / deletion endpoints.

FastAPI is imported lazily (via `ctxloom._extras`): the module imports without
fastapi installed, and only `create_chat_router` requires the `web` extra —
`pip install "ctxloom[web]"`.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from ._extras import require_extra
from .chat import ChatAssistant

if TYPE_CHECKING:
    from fastapi import APIRouter
    from fastapi.responses import JSONResponse, StreamingResponse


class ChatMessage(BaseModel):
    """Wire shape of an incoming user turn."""

    message: str
    session_id: str = ""


def sse(event_type: str, data: dict[str, Any]) -> str:
    """Formats one Server-Sent-Events frame."""
    return f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def create_chat_router(
    assistant: ChatAssistant,
    *,
    prefix: str = "/api",
    with_health: bool = True,
) -> APIRouter:
    """Builds the chat router on top of a `ChatAssistant`.

    Routes (default prefix `/api`):
      POST   /api/chat/stream       — SSE turn (session → status… → message)
      GET    /api/runs/{id}         — reconstructed chat thread
      DELETE /api/runs/{id}         — delete a session's history
      GET    /api/health            — liveness (opt-out via `with_health=False`)
    """
    # Readable error when the `web` extra is missing — then a regular
    # (mypy-visible) import for the real types.
    require_extra("web.create_chat_router", "fastapi", "web")
    from fastapi import APIRouter
    from fastapi.responses import JSONResponse, StreamingResponse

    router = APIRouter(prefix=prefix)

    if with_health:

        @router.get("/health")
        async def health() -> dict[str, bool]:
            return {"ok": True}

    @router.post("/chat/stream")
    async def chat_stream(req: ChatMessage) -> StreamingResponse:
        async def stream() -> AsyncIterator[str]:
            async for event in assistant.stream(req.message, req.session_id):
                if event.kind == "session":
                    yield sse("session", {"session_id": event.session_id})
                elif event.kind == "status":
                    yield sse("status", {"message": event.message})
                elif event.kind == "message":
                    yield sse("message", event.payload or {"reply": ""})

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @router.get("/runs/{session_id}")
    async def runs(session_id: str) -> JSONResponse:
        return JSONResponse(assistant.history(session_id))

    @router.delete("/runs/{session_id}")
    async def run_delete(session_id: str) -> dict[str, bool]:
        assistant.store.delete_session(session_id)
        return {"ok": True}

    return router


__all__ = ["ChatMessage", "create_chat_router", "sse"]
