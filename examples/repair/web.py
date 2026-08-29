"""FastAPI + SSE backend for the repair assistant (CTXSPACE).

A port of REPAIR_AI_CHAT (LangGraph) — to compare the pipeline and its effect
head-to-head. SSE contract:

  event: session  — session id
  event: status   — progress («Думаю…», «Составляю план…», «Считаю смету…»)
  event: message  — terminal reply {reply, waiting}; waiting=true = HITL approval

Run:  .venv/bin/python examples/repair/web.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

if __package__ in (None, ""):  # run as a script — add src to sys.path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ctxloom import (
    Budget,
    Context,
    FileKVBackend,
    Runtime,
    RuntimeResources,
    SessionStore,
)
from ctxloom.providers import (
    embedder_from_env,
    image_from_env,
    llm_from_env,
    openrouter_llm,
)
from dotenv import load_dotenv
from examples.repair.agents import RepairFlow
from examples.repair.models import ChatReply, Project, UserMsg
from examples.repair.services import Catalog
from fastapi import FastAPI
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

load_dotenv()

ROOT = Path(__file__).resolve().parent


class ChatRequest(BaseModel):
    message: str
    session_id: str


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


FALLBACK_REPLY = "Не удалось обработать запрос. Попробуйте ещё раз."


def _resources(llm) -> RuntimeResources:
    resources = RuntimeResources(llm=llm)
    resources.set("catalog", Catalog(ROOT / "data" / "price.csv"))
    resources.set("images_dir", str(ROOT / "web" / "assets" / "generated"))
    embedder = embedder_from_env()
    if embedder is not None:
        resources.embedder = embedder
    images = image_from_env()
    if images is not None:
        resources.set("images", images)
    return resources


def _session_state(ctx: Context) -> dict:
    msgs: list[dict] = [
        {"role": "user", "text": m.data.text, "at": m.created_at.isoformat()}
        for m in ctx.list_artifacts(UserMsg)
    ]
    replies: list[dict] = [
        {"role": "assistant", "text": r.data.text, "at": r.created_at.isoformat()}
        for r in ctx.list_artifacts(ChatReply)
    ]
    turns = sorted(msgs + replies, key=lambda item: item["at"])
    projects = ctx.list_artifacts(Project)
    project = projects[0].data if projects else None
    return {
        "messages": turns,
        "stage": project.stage if project else "",
        "approved": project.approved if project else False,
        "plan": [s.model_dump() for s in project.plan] if project else [],
        "estimate": (
            project.estimate.model_dump() if project and project.estimate else None
        ),
    }


def create_app(db=None, llm=None, store_dir: str | None = None) -> FastAPI:
    """Application factory. `llm` and `store_dir` are for tests; by default the
    providers come from .env (OpenRouter·DeepSeek for chat)."""
    active_llm = llm if llm is not None else (llm_from_env() or openrouter_llm())
    store = SessionStore(
        FileKVBackend(str(Path(store_dir) if store_dir else ROOT / "sessions"))
    )

    app = FastAPI(title="repair-ai (ctxloom)")

    @app.get("/api/health")
    async def health() -> dict:
        return {"ok": True}

    @app.post("/api/chat/stream")
    async def chat_stream(req: ChatRequest) -> StreamingResponse:
        session = store.open(req.session_id, resources=_resources(active_llm))
        runtime = Runtime(
            session.context,
            agents=[RepairFlow()],
            session=session,
            budget=Budget(max_runs=200),
            max_concurrency=2,
        )
        msg = session.context.create(
            UserMsg(text=req.message, session_id=req.session_id)
        )

        async def stream():
            yield _sse("session", {"session_id": req.session_id})
            try:
                async for event in runtime.astream():
                    if event.kind == "status":
                        yield _sse("status", {"message": event.message})
            except Exception:
                # the runtime crashed — an honest fallback instead of a broken channel (§59)
                yield _sse("message", {"reply": FALLBACK_REPLY, "waiting": False})
                return
            pending = [
                q
                for q in session.context.pending_questions()
                if q.data.kind == "approval"
            ]
            if pending:
                yield _sse(
                    "message", {"reply": pending[0].data.question, "waiting": True}
                )
            else:
                replies = [
                    r
                    for r in session.context.list_artifacts(ChatReply)
                    if r.data.query_id == msg.id
                ]
                reply = max(replies, key=lambda r: r.created_at) if replies else None
                yield _sse(
                    "message",
                    {
                        "reply": reply.data.text if reply else FALLBACK_REPLY,
                        "waiting": False,
                        "images": reply.data.images if reply else [],
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
            return JSONResponse({"messages": [], "stage": ""})
        return JSONResponse(_session_state(session.context))

    @app.delete("/api/runs/{session_id}")
    async def run_delete(session_id: str) -> dict:
        store.delete_session(session_id)
        return {"ok": True}

    web_dir = ROOT / "web"
    if web_dir.exists():
        app.mount("/", StaticFiles(directory=str(web_dir), html=True), name="web")
    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "examples.repair.web:create_app", factory=True, host="127.0.0.1", port=8000
    )
