"""FastAPI + SSE backend for the repair assistant (CTXSPACE).

A port of REPAIR_AI_CHAT (LangGraph) — to compare the pipeline and its effect
head-to-head. The transport is the canonical ctxloom chat contract
(`ctxloom.chat` + `ctxloom.web` router); the domain twist is the HITL approval
gate: a pending `approval` question → `waiting: true` instead of a reply.

Run:  .venv/bin/python examples/repair/web.py
"""

from __future__ import annotations

import sys
from pathlib import Path

if __package__ in (None, ""):  # run as a script — add src to sys.path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ctxloom import (
    Budget,
    ChatAssistant,
    Context,
    FileKVBackend,
    RuntimeResources,
    SessionStore,
)
from ctxloom.providers import (
    embedder_from_env,
    image_from_env,
    llm_from_env,
    openrouter_llm,
)
from ctxloom.web import create_chat_router
from dotenv import load_dotenv
from examples.repair.agents import RepairFlow
from examples.repair.models import ChatReply, Project, UserMsg
from examples.repair.services import Catalog
from fastapi import FastAPI, Response
from fastapi.staticfiles import StaticFiles

load_dotenv()

ROOT = Path(__file__).resolve().parent

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


def terminal_reply(ctx: Context, msg_id: str) -> dict:
    """Terminal reply: a pending approval → waiting:true, else the ChatReply."""
    pending = [q for q in ctx.pending_questions() if q.data.kind == "approval"]
    if pending:
        return {"reply": pending[0].data.question, "waiting": True}
    replies = [r for r in ctx.list_artifacts(ChatReply) if r.data.query_id == msg_id]
    reply = max(replies, key=lambda r: r.created_at) if replies else None
    return {
        "reply": reply.data.text if reply else FALLBACK_REPLY,
        "waiting": False,
        "images": reply.data.images if reply else [],
    }


def session_state(ctx: Context) -> dict:
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
            {
                **project.estimate.model_dump(),
                "budget": project.info.budget,
            }
            if project and project.estimate
            else None
        ),
    }


def create_app(db=None, llm=None, store_dir: str | None = None) -> FastAPI:
    """Application factory. `llm` and `store_dir` are for tests; by default the
    providers come from .env (OpenRouter·DeepSeek for chat)."""
    active_llm = llm if llm is not None else (llm_from_env() or openrouter_llm())
    store = SessionStore(
        FileKVBackend(str(Path(store_dir) if store_dir else ROOT / "sessions"))
    )

    assistant = ChatAssistant(
        store=store,
        agents=[RepairFlow()],
        user_message=UserMsg,
        reply=terminal_reply,
        session_state=session_state,
        resources=lambda: _resources(active_llm),
        budget=Budget(max_runs=200),
        max_concurrency=2,
    )

    app = FastAPI(title="repair-ai (ctxloom)")
    app.include_router(create_chat_router(assistant))

    @app.get("/api/runs/{session_id}/estimate.csv")
    async def estimate_csv(session_id: str) -> Response:
        """The approved plan + estimate as a CSV worksheet (Excel-ready, §58)."""
        from examples.repair.models import Project
        from examples.repair.services.estimate import estimate_to_csv

        session = store.open(session_id)
        context = session.context if session.loaded else None
        project = (
            context.list_artifacts(Project)[0].data
            if context is not None and context.list_artifacts(Project)
            else None
        )
        if project is None or project.estimate is None:
            return Response(status_code=404)
        return Response(
            content=estimate_to_csv(project),
            media_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": 'attachment; filename="smeta.csv"',
            },
        )

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
