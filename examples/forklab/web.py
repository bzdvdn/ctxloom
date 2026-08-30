"""forklab web — FastAPI + SSE demo of the fork → merge pipeline (§39-§40).

Single-shot: type a question, the server forks two research branches, streams
their progress (`status` events), merges them three-way (explicit conflicts,
§40), synthesizes the answer, and returns it with the merged provenance graph:

    event: status  — progress lines ("depth: wording 1 finding…", "merging…")
    event: result  — {answer, sources, splits, version, mermaid}
    event: message — honest fallback on failure (§59)

Run:  .venv/bin/python examples/forklab/web.py
"""

from __future__ import annotations

import json
import sys
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

if __package__ in (None, ""):  # run as a script — add repo root to sys.path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ctxloom.providers import LLMProvider, llm_from_env
from ctxloom.viz import context_to_mermaid
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from examples.forklab.pipeline import (
    evaluate_runtime,
    investigate_runtime,
    make_fork,
    merge_forks,
    result_data,
)

load_dotenv()

ROOT = Path(__file__).resolve().parent
FALLBACK_REPLY = "Не удалось обработать запрос. Попробуйте ещё раз."


class AskRequest(BaseModel):
    message: str
    topic: str | None = None


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def create_app(llm: LLMProvider | None = None) -> FastAPI:
    """App factory. `llm` is for tests; by default it comes from `.env` (§68)."""
    active_llm = llm if llm is not None else llm_from_env()
    app = FastAPI(title="fork-lab (ctxloom)")

    @app.get("/api/health")
    async def health() -> dict[str, Any]:
        return {"ok": True}

    @app.post("/api/ask/stream")
    async def ask_stream(req: AskRequest) -> StreamingResponse:
        topic = req.topic or "thermal energy recovery in HVAC design"

        async def stream() -> AsyncIterator[str]:
            try:
                yield _sse(
                    "status",
                    {"message": "preparing base + two forks (depth / breadth)"},
                )
                depth = make_fork(
                    req.message, topic, name="depth", kind="depth", llm=active_llm
                )
                breadth = make_fork(
                    req.message, topic, name="breadth", kind="breadth", llm=active_llm
                )

                yield _sse("status", {"message": "depth branch: investigating…"})
                async for event in investigate_runtime(depth).astream():
                    if event.kind == "status":
                        yield _sse("status", {"message": event.message})

                yield _sse("status", {"message": "breadth branch: investigating…"})
                async for event in investigate_runtime(breadth).astream():
                    if event.kind == "status":
                        yield _sse("status", {"message": event.message})

                yield _sse("status", {"message": "merging branches (three-way, §40)…"})
                merge_forks(depth, breadth)

                async for event in evaluate_runtime(depth).astream():
                    if event.kind == "status":
                        yield _sse("status", {"message": event.message})

                data = result_data(depth)
                if not data["answer"]:  # honest fallback, §59
                    yield _sse("message", {"reply": FALLBACK_REPLY, "waiting": False})
                    return
                yield _sse(
                    "result",
                    {
                        **data,
                        "mermaid": context_to_mermaid(depth),
                    },
                )
            except Exception:  # the pipeline crashed — an honest fallback (§59)
                yield _sse("message", {"reply": FALLBACK_REPLY, "waiting": False})

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    web_dir = ROOT / "web"
    if web_dir.exists():
        app.mount("/", StaticFiles(directory=str(web_dir), html=True), name="web")
    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "examples.forklab.web:create_app", factory=True, host="127.0.0.1", port=8000
    )
