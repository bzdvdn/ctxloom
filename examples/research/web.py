"""FastAPI + SSE for the research demo (goes to the web for data, §32).

SSE contract (session / status / message). Run:  .venv/bin/python examples/research/web.py
"""

from __future__ import annotations

import json
import sys
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ctxloom import Budget, FileKVBackend, Runtime, SessionStore
from fastapi import FastAPI
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from examples.research.agents import research_agents
from examples.research.chat import build_resources
from examples.research.models import Answer, UserQuery

ROOT = Path(__file__).resolve().parent
FALLBACK_REPLY = "No answer was assembled. Try rephrasing the question."


class ChatRequest(BaseModel):
    message: str
    session_id: str


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _terminal_reply(ctx: Any, msg_id: str) -> dict[str, Any]:
    answers = [a for a in ctx.list_artifacts(Answer) if a.data.query_id == msg_id]
    if answers:
        answer = max(answers, key=lambda a: a.created_at).data
        return {"reply": answer.text, "waiting": False, "sources": answer.sources}
    return {"reply": FALLBACK_REPLY, "waiting": False, "sources": []}


def create_app(store_dir: str | None = None) -> FastAPI:
    """Factory; `store_dir` is for tests (temp sessions)."""
    store = SessionStore(
        FileKVBackend(str(Path(store_dir) if store_dir else ROOT / "sessions"))
    )

    app = FastAPI(title="research-ai (ctxloom)")

    @app.get("/api/health")
    async def health() -> dict[str, Any]:
        return {"ok": True}

    @app.post("/api/chat/stream")
    async def chat_stream(req: ChatRequest) -> StreamingResponse:
        resources = build_resources()
        session = store.open(req.session_id, resources=resources)
        runtime = Runtime(
            session.context,
            agents=research_agents(),
            session=session,
            budget=Budget(max_runs=200),
            max_concurrency=4,
        )
        msg = session.context.create(
            UserQuery(text=req.message, session_id=req.session_id)
        )

        async def stream() -> AsyncIterator[str]:
            yield _sse("session", {"session_id": req.session_id})
            try:
                async for event in runtime.astream():
                    if event.kind == "status":
                        yield _sse("status", {"message": event.message})
            except Exception:
                yield _sse(
                    "message",
                    {"reply": FALLBACK_REPLY, "waiting": False, "sources": []},
                )
                return
            yield _sse("message", _terminal_reply(session.context, msg.id))
            session.save()

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/api/runs/{session_id}")
    async def runs(session_id: str) -> JSONResponse:
        session = store.open(session_id)
        return JSONResponse(
            {
                "messages": [
                    {"role": "user", "text": m.data.text}
                    for m in session.context.list_artifacts(UserQuery)
                ]
                + [
                    {"role": "assistant", "text": a.data.text}
                    for a in session.context.list_artifacts(Answer)
                ]
            }
        )

    @app.delete("/api/runs/{session_id}")
    async def run_delete(session_id: str) -> dict[str, str]:
        store.delete_session(session_id)
        return {"ok": "true"}

    web_dir = ROOT / "web"
    if web_dir.exists():
        app.mount("/", StaticFiles(directory=str(web_dir), html=True), name="web")
    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "examples.research.web:create_app", factory=True, host="127.0.0.1", port=8001
    )
