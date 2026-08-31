"""FastAPI + SSE for the devops assistant (k8s / GitLab / Ansible).

The transport is the canonical ctxloom chat contract (`ctxloom.chat` +
`ctxloom.web` router). The one domain twist: when an agent is waiting for
clarification (HITL), the next user message is an *answer* — `create_message`
resumes the pending question instead of appending a new artifact.

Run:  .venv/bin/python examples/devops/web.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):  # running as a script — add src to sys.path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ctxloom import (
    Budget,
    ChatAssistant,
    FileKVBackend,
    RuntimeResources,
    SessionStore,
    Tracer,
    TraceStore,
)
from ctxloom.providers import llm_from_env, openrouter_llm
from ctxloom.tracing.web import create_trace_router
from ctxloom.web import create_chat_router
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
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

FALLBACK_REPLY = "Failed to assemble the answer. Try rephrasing the question."

AGENTS = [RouteAgent(), K8sAgent(), GitlabAgent(), AnsibleAgent(), RenderAgent()]


def _resources(llm) -> RuntimeResources:
    return RuntimeResources(llm=llm)


def create_message(ctx: Any, text: str) -> str:
    """HITL enter hook: a pending clarify question → resume, else a new message."""
    pending = [q for q in ctx.pending_questions() if q.data.kind == "clarify"]
    if pending:
        question = pending[0]
        ctx.resume(question.id, text)
        qid = question.data.notes.get("query_id") or ""
        problem = ctx.get(qid)
        return getattr(problem.data, "query_id", "") if problem else ""
    return ctx.create(UserMsg(text=text, session_id="")).id


def terminal_reply(ctx: Any, msg_id: str) -> dict[str, Any]:
    """Terminal reply: a pending question → waiting:true, else the ChatReply."""
    waiting = [q for q in ctx.pending_questions() if q.data.kind == "clarify"]
    if waiting:
        return {"reply": waiting[0].data.question, "waiting": True}
    replies = [r for r in ctx.list_artifacts(ChatReply) if r.data.query_id == msg_id]
    reply = max(replies, key=lambda r: r.created_at) if replies else None
    return {"reply": reply.data.text if reply else FALLBACK_REPLY, "waiting": False}


def session_state(ctx: Any) -> dict:
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

    assistant = ChatAssistant(
        store=store,
        agents=AGENTS,
        user_message=UserMsg,
        reply=terminal_reply,
        session_state=session_state,
        create_message=create_message,
        resources=lambda: _resources(active_llm),
        budget=Budget(max_runs=200, max_tool_calls=12),
        tracer=lambda: Tracer(store=trace_store),
        status_kinds=("status", "agent"),
    )

    app = FastAPI(title="devops-ai (ctxloom)")
    app.include_router(
        create_trace_router(
            trace_store,
            username=os.environ.get("TRACE_USER") or None,
            password=os.environ.get("TRACE_PASSWORD") or None,
        )
    )
    app.include_router(create_chat_router(assistant))

    web_dir = ROOT / "web"
    if web_dir.exists():
        app.mount("/", StaticFiles(directory=str(web_dir), html=True), name="web")
    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "examples.devops.web:create_app", factory=True, host="127.0.0.1", port=8000
    )
