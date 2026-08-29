"""FastAPI router for viewing traces (§54).

Mounted in the app: `app.include_router(create_trace_router(store))`.
Serves a JSON API (`/api/traces`, `/api/traces/{id}`), a `/traces` list, and a
trace page `/traces/{id}` (templates in `templates/`). Polling provides "real
time".

FastAPI is imported lazily inside `create_trace_router`: the module itself and the whole
`tracing` package do not require fastapi installed — it is needed only where
the router is created (a web app).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .store import TraceStore

if TYPE_CHECKING:
    from fastapi import APIRouter

_TEMPLATES = Path(__file__).parent / "templates"


def create_trace_router(
    store: TraceStore,
    *,
    username: str | None = None,
    password: str | None = None,
) -> APIRouter:
    """Router over the SQLite trace store.

    Returns `fastapi.APIRouter`; fastapi is imported here (lazily)
    so that `ctxloom.tracing.web` works without it.

    If `username`/`password` are set — all handlers (including UI pages)
    are protected with HTTP Basic auth. Traces contain full prompts and
    artifact contents — do not expose them without auth.
    """
    import secrets

    from fastapi import APIRouter, Depends, HTTPException, Query
    from fastapi.responses import HTMLResponse
    from fastapi.security import HTTPBasic, HTTPBasicCredentials

    dependencies = []
    if username is not None and password is not None:
        security = HTTPBasic(auto_error=False)
        expected_user = username
        expected_pass = password

        def _check(
            credentials: HTTPBasicCredentials | None = Depends(  # noqa: B008
                security
            ),
        ) -> None:
            if credentials is None or not (
                secrets.compare_digest(credentials.username, expected_user)
                and secrets.compare_digest(credentials.password, expected_pass)
            ):
                raise HTTPException(
                    status_code=401,
                    detail="Unauthorized",
                    headers={"WWW-Authenticate": "Basic"},
                )

        dependencies = [Depends(_check)]

    router = APIRouter(dependencies=dependencies)

    @router.get("/api/traces")
    async def list_traces(
        session_id: str | None = Query(default=None),
        outcome: str | None = Query(default=None),
        limit: int = Query(default=25, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
    ) -> dict[str, Any]:
        return store.query(
            session_id=session_id, outcome=outcome, limit=limit, offset=offset
        )

    @router.get("/api/traces/{trace_id}")
    async def get_trace(trace_id: str) -> dict[str, Any]:
        trace = store.get(trace_id)
        if trace is None:
            raise HTTPException(status_code=404, detail="trace not found")
        return trace.to_dict()

    @router.get("/traces", response_class=HTMLResponse)
    async def traces_list_page() -> str:
        return (_TEMPLATES / "ui.html").read_text(encoding="utf-8")

    @router.get("/traces/{trace_id}", response_class=HTMLResponse)
    async def traces_run_page(trace_id: str) -> str:
        return (
            (_TEMPLATES / "ui_run.html")
            .read_text(encoding="utf-8")
            .replace("__RUN_ID__", json.dumps(trace_id))
        )

    return router
