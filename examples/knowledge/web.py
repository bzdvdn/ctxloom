"""FastAPI + SSE for a knowledge chat (multi-source assistant, CTXSPACE).

SSE contract (like the repair assistant):

  event: session  — session id
  event: status   — progress («Searching for info…», «Found N…», «Assembling the answer…»)
  event: message  — terminal reply {reply, waiting, sources}

Reply — an Answer with a source list (evidence-backed, §17) or a ChatReply.

Run:  .venv/bin/python examples/knowledge/web.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

if __package__ in (None, ""):  # run as a script — add src to sys.path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ctxloom import (
    Budget,
    FileKVBackend,
    Runtime,
    RuntimeResources,
    SessionStore,
)
from ctxloom.providers import llm_from_env, openrouter_llm
from ctxloom.sources import CSVSource, FileSystemSource
from dotenv import load_dotenv
from examples.knowledge.agents import (
    AnswerBuilder,
    CalculatorAgent,
    EvidenceBuilder,
    Planner,
    ProgressEvaluator,
    ResolverAgent,
    SearchScout,
    TableResolver,
    VerifierAgent,
)
from examples.knowledge.models import (
    Answer,
    Calculation,
    ChatReply,
    Claim,
    UserQuery,
)
from examples.textutil import english_kw_score
from fastapi import FastAPI
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

DOCS_DIR = ROOT / "docs"
FALLBACK_REPLY = "Failed to assemble an answer. Try rephrasing the question."


class ChatRequest(BaseModel):
    message: str
    session_id: str


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _resources(llm) -> RuntimeResources:
    return RuntimeResources(
        llm=llm,
        sources={
            "guide": FileSystemSource(
                str(DOCS_DIR / "guide"), source_id="guide", scorer=english_kw_score
            ),
            "pricing": FileSystemSource(
                str(DOCS_DIR / "pricing"),
                source_id="pricing",
                scorer=english_kw_score,
            ),
            "costs": CSVSource(str(DOCS_DIR / "costs"), source_id="costs"),
        },
    )


def _session_state(ctx) -> dict:
    msgs: list[dict] = [
        {"role": "user", "text": m.data.text, "at": m.created_at.isoformat()}
        for m in ctx.list_artifacts(UserQuery)
    ]
    for r in ctx.list_artifacts(ChatReply):
        msgs.append(
            {"role": "assistant", "text": r.data.text, "at": r.created_at.isoformat()}
        )
    for a in ctx.list_artifacts(Answer):
        text = a.data.text
        if a.data.sources:
            text += "\n\nSources:\n" + "\n".join(f"• {s}" for s in a.data.sources)
        msgs.append({"role": "assistant", "text": text, "at": a.created_at.isoformat()})
    msgs.sort(key=lambda item: item["at"])
    return {"messages": msgs}


def _terminal_reply(ctx, msg_id: str) -> dict:
    """Terminal reply for a message: Answer → ChatReply → insufficient."""
    answers = [a for a in ctx.list_artifacts(Answer) if a.data.query_id == msg_id]
    if answers:
        answer = max(answers, key=lambda a: a.created_at).data
        claims = [
            {
                "text": c.data.text,
                "confidence": c.data.confidence,
                "status": "conflict" if c.data.conflict else c.data.status,
            }
            for c in ctx.list_artifacts(Claim)
            if c.data.query_id == msg_id
        ]
        calculations = [
            {
                "description": c.data.description,
                "value": c.data.value,
                "column": c.data.column,
            }
            for c in ctx.list_artifacts(Calculation)
            if c.data.query_id == msg_id
        ]
        return {
            "reply": answer.text,
            "waiting": False,
            "sources": answer.sources,
            "claims": claims,
            "calculations": calculations,
        }
    replies = [r for r in ctx.list_artifacts(ChatReply) if r.data.query_id == msg_id]
    if replies:
        latest = max(replies, key=lambda r: r.created_at)
        return {"reply": latest.data.text, "waiting": False, "sources": []}
    return {"reply": FALLBACK_REPLY, "waiting": False, "sources": []}


def create_app(db=None, llm=None, store_dir: str | None = None) -> FastAPI:
    """App factory. `llm` and `store_dir` are for tests; by default the
    providers come from .env (OpenRouter·DeepSeek for chat)."""
    active_llm = llm if llm is not None else (llm_from_env() or openrouter_llm())
    store = SessionStore(
        FileKVBackend(str(Path(store_dir) if store_dir else ROOT / "sessions"))
    )

    app = FastAPI(title="knowledge-ai (ctxspace)")

    @app.get("/api/health")
    async def health() -> dict:
        return {"ok": True}

    @app.post("/api/chat/stream")
    async def chat_stream(req: ChatRequest) -> StreamingResponse:
        session = store.open(req.session_id, resources=_resources(active_llm))
        runtime = Runtime(
            session.context,
            agents=[
                Planner(),
                SearchScout(),
                ResolverAgent(),
                TableResolver(),
                EvidenceBuilder(),
                VerifierAgent(),
                CalculatorAgent(),
                ProgressEvaluator(),
                AnswerBuilder(),
            ],
            session=session,
            budget=Budget(max_runs=200),
            max_concurrency=4,
        )
        msg = session.context.create(
            UserQuery(text=req.message, session_id=req.session_id)
        )

        async def stream():
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


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "examples.knowledge.web:create_app", factory=True, host="127.0.0.1", port=8000
    )
