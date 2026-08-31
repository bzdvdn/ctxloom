"""FastAPI + SSE for the research demo (goes to the web for data, §32).

The transport is the canonical ctxloom chat contract (`ctxloom.chat` +
`ctxloom.web` router); this file only supplies the domain hooks: agents,
input artifact type, terminal reply and history.

Run:  .venv/bin/python examples/research/web.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ctxloom import (
    Budget,
    ChatAssistant,
    FileKVBackend,
    SessionStore,
)
from ctxloom.web import create_chat_router
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from examples.research.agents import research_agents
from examples.research.chat import build_resources
from examples.research.models import Answer, UserQuery

ROOT = Path(__file__).resolve().parent
FALLBACK_REPLY = "No answer was assembled. Try rephrasing the question."


def terminal_reply(ctx: Any, msg_id: str) -> dict[str, Any]:
    answers = [a for a in ctx.list_artifacts(Answer) if a.data.query_id == msg_id]
    if answers:
        answer = max(answers, key=lambda a: a.created_at).data
        return {"reply": answer.text, "waiting": False, "sources": answer.sources}
    return {"reply": FALLBACK_REPLY, "waiting": False, "sources": []}


def session_state(ctx: Any) -> dict[str, Any]:
    return {
        "messages": [
            {"role": "user", "text": m.data.text} for m in ctx.list_artifacts(UserQuery)
        ]
        + [
            {"role": "assistant", "text": a.data.text}
            for a in ctx.list_artifacts(Answer)
        ]
    }


def create_app(store_dir: str | None = None) -> FastAPI:
    """Factory; `store_dir` is for tests (temp sessions)."""
    store = SessionStore(
        FileKVBackend(str(Path(store_dir) if store_dir else ROOT / "sessions"))
    )
    assistant = ChatAssistant(
        store=store,
        agents=research_agents,
        user_message=UserQuery,
        reply=terminal_reply,
        session_state=session_state,
        resources=build_resources,
        budget=Budget(max_runs=200),
        max_concurrency=4,
    )

    app = FastAPI(title="research-ai (ctxloom)")
    app.include_router(create_chat_router(assistant))

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
