"""FastAPI + SSE for the devops assistant (k8s / GitLab / Ansible).

SSE contract (as in repair/knowledge): session → status → message.
Run:  .venv/bin/python examples/devops/web.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

if __package__ in (None, ""):  # running as a script — add src to sys.path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ctxloom import (
    Budget,
    FileKVBackend,
    Runtime,
    RuntimeResources,
    SessionStore,
    Tracer,
    TraceStore,
)
from ctxloom.providers import llm_from_env, openrouter_llm
from ctxloom.tracing.web import create_trace_router
from dotenv import load_dotenv
from examples.devops.agents import (
    AnsibleAgent,
    GitlabAgent,
    K8sAgent,
    RenderAgent,
    RouteAgent,
)
from examples.devops.models import ChatReply, UserMsg
from fastapi import FastAPI
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

FALLBACK_REPLY = "Failed to assemble the answer. Try rephrasing the question."


class ChatRequest(BaseModel):
    message: str
    session_id: str


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _resources(llm) -> RuntimeResources:
    return RuntimeResources(llm=llm)


def _session_state(ctx) -> dict:
    msgs: list[dict] = [
        {"role": "user", "text": m.data.text, "at": m.created_at.isoformat()}
        for m in ctx.list_artifacts(UserMsg)
    ]
    for r in ctx.list_artifacts(ChatReply):
        msgs.append(
            {"role": "assistant", "text": r.data.text, "at": r.created_at.isoformat()}
        )
    msgs.sort(key=lambda item: item["at"])
    return {"messages": msgs}


def create_app(db=None, llm=None, store_dir: str | None = None) -> FastAPI:
    """App factory. `llm` and `store_dir` — for tests; by default the
    providers come from .env (OpenRouter·DeepSeek)."""
    active_llm = llm if llm is not None else (llm_from_env() or openrouter_llm())
    store = SessionStore(
        FileKVBackend(str(Path(store_dir) if store_dir else ROOT / "sessions"))
    )
    trace_store = TraceStore(
        str(Path(store_dir) / "traces.db") if store_dir else str(ROOT / "traces.db")
    )

    app = FastAPI(title="devops-ai (ctxloom)")
    app.include_router(
        create_trace_router(
            trace_store,
            username=os.environ.get("TRACE_USER") or None,
            password=os.environ.get("TRACE_PASSWORD") or None,
        )
    )

    @app.get("/api/health")
    async def health() -> dict:
        return {"ok": True}

    @app.post("/api/chat/stream")
    async def chat_stream(req: ChatRequest) -> StreamingResponse:
        session = store.open(req.session_id, resources=_resources(active_llm))
        runtime = Runtime(
            session.context,
            agents=[
                RouteAgent(),
                K8sAgent(),
                GitlabAgent(),
                AnsibleAgent(),
                RenderAgent(),
            ],
            session=session,
            budget=Budget(max_runs=200, max_tool_calls=12),
            tracer=Tracer(store=trace_store),
        )
        # If the agent is waiting for clarification (HITL), this is an answer to a question, not a new request.
        pending = [
            q for q in session.context.pending_questions() if q.data.kind == "clarify"
        ]
        if pending:
            question = pending[0]
            session.context.resume(question.id, req.message)
            qid = question.data.notes.get("query_id") or ""
            problem = session.context.get(qid)
            msg_id = getattr(problem.data, "query_id", "") if problem else ""
        else:
            msg_id = session.context.create(
                UserMsg(text=req.message, session_id=req.session_id)
            ).id

        async def stream():
            yield _sse("session", {"session_id": req.session_id})
            try:
                async for event in runtime.astream():
                    if event.kind in ("status", "agent"):
                        yield _sse("status", {"message": event.message})
            except Exception:
                yield _sse("message", {"reply": FALLBACK_REPLY, "waiting": False})
                return
            waiting = [
                q
                for q in session.context.pending_questions()
                if q.data.kind == "clarify"
            ]
            if waiting:
                yield _sse(
                    "message",
                    {"reply": waiting[0].data.question, "waiting": True},
                )
            else:
                replies = [
                    r
                    for r in session.context.list_artifacts(ChatReply)
                    if r.data.query_id == msg_id
                ]
                reply = max(replies, key=lambda r: r.created_at) if replies else None
                yield _sse(
                    "message",
                    {
                        "reply": reply.data.text if reply else FALLBACK_REPLY,
                        "waiting": False,
                    },
                )
            session.save()

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/api/runs/{session_id}")
    async def runs(session_id: str) -> JSONResponse:
        session = store.open(session_id)
        if not session.loaded:
            return JSONResponse({"messages": []})
        return JSONResponse(_session_state(session.context))

    @app.delete("/api/runs/{session_id}")
    async def run_delete(session_id: str) -> dict:
        store.delete_session(session_id)
        return {"ok": True}

    web_dir = ROOT / "web"
    if web_dir.exists():
        app.mount("/", StaticFiles(directory=str(web_dir), html=True), name="web")
    return app


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "examples.devops.web:create_app", factory=True, host="127.0.0.1", port=8000
    )
