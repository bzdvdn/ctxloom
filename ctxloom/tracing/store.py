"""Trace sinks: what accepts a finished `RunTrace`.

`TraceStore` is the SQLite sink (`runs`/`spans` tables). Pattern as in teff:
the exporter writes the trace, and the observer (`Tracer`) decides where to push. Later —
Langfuse and Postgres sinks with the same `export` interface.
"""

from __future__ import annotations

import json
import sqlite3
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from .models import AgentSpan, ArtifactRef, LLMCall, RunTrace


class TraceSink(Protocol):
    """Interface for trace sinks (SQLite, Langfuse, Postgres…)."""

    def export(self, trace: RunTrace) -> None: ...


class TraceStore:
    """SQLite trace sink: writes `RunTrace` and can serve them back."""

    def __init__(
        self,
        path: str = "traces.db",
        *,
        timeout: float = 10.0,
        max_runs: int | None = 200,
    ):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.max_runs = max_runs
        self._conn = sqlite3.connect(path, check_same_thread=False, timeout=timeout)
        self._create_schema()
        self._migrate()

    def close(self) -> None:
        self._conn.close()

    def _create_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS runs (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL DEFAULT '',
                started_at REAL NOT NULL,
                duration_ms REAL NOT NULL,
                outcome TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS spans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL REFERENCES runs(id),
                agent TEXT NOT NULL,
                event_type TEXT NOT NULL DEFAULT '',
                latency_ms REAL NOT NULL DEFAULT 0,
                error TEXT,
                reads TEXT NOT NULL DEFAULT '[]',
                writes TEXT NOT NULL DEFAULT '[]',
                llm_calls TEXT NOT NULL DEFAULT '[]'
            );
            CREATE INDEX IF NOT EXISTS idx_spans_run ON spans(run_id);
            """
        )
        self._conn.commit()

    def _migrate(self) -> None:
        """Adds columns that appeared after the old schema (like teff)."""
        try:
            cols = {row[1] for row in self._conn.execute("PRAGMA table_info(spans)")}
        except sqlite3.OperationalError:
            return
        if "llm_calls" not in cols:
            self._conn.execute(
                "ALTER TABLE spans ADD COLUMN llm_calls TEXT NOT NULL DEFAULT '[]'"
            )
            self._conn.commit()

    def export(self, trace: RunTrace) -> None:
        started = trace.started_at.timestamp() if trace.started_at else time.time()
        self._conn.execute(
            "INSERT INTO runs (id, session_id, started_at, duration_ms, outcome) "
            "VALUES (?, ?, ?, ?, ?)",
            (trace.id, trace.session_id, started, trace.duration_ms, trace.outcome),
        )
        for span in trace.spans:
            self._conn.execute(
                "INSERT INTO spans (run_id, agent, event_type, latency_ms, error, "
                "reads, writes, llm_calls) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    trace.id,
                    span.agent,
                    span.event_type,
                    span.latency_ms,
                    span.error,
                    json.dumps([r.model_dump(mode="json") for r in span.reads]),
                    json.dumps([w.model_dump(mode="json") for w in span.writes]),
                    json.dumps([c.model_dump(mode="json") for c in span.llm_calls]),
                ),
            )
        self._conn.commit()
        if self.max_runs is not None:
            self.prune(self.max_runs)

    def prune(self, keep: int) -> int:
        """Keeps the last `keep` traces, deletes older ones (retention)."""
        cur = self._conn.execute(
            "DELETE FROM runs WHERE id NOT IN "
            "(SELECT id FROM runs ORDER BY started_at DESC LIMIT ?)",
            (keep,),
        )
        self._conn.execute(
            "DELETE FROM spans WHERE run_id NOT IN (SELECT id FROM runs)"
        )
        self._conn.commit()
        return cur.rowcount

    def query(
        self,
        *,
        session_id: str | None = None,
        outcome: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Latest traces with filters and pagination (§54).

        Returns ``{"items": [...], "total": n}``, where total is before pagination.
        """
        where: list[str] = []
        args: list[Any] = []
        if session_id is not None:
            where.append("session_id = ?")
            args.append(session_id)
        if outcome is not None:
            where.append("outcome = ?")
            args.append(outcome)
        where_sql = (" WHERE " + " AND ".join(where)) if where else ""

        total = self._conn.execute(
            f"SELECT COUNT(*) FROM runs{where_sql}", tuple(args)
        ).fetchone()[0]
        rows = self._conn.execute(
            f"SELECT id, session_id, started_at, duration_ms, outcome, "
            f"(SELECT COUNT(*) FROM spans WHERE run_id = runs.id) AS spans_count "
            f"FROM runs{where_sql} ORDER BY started_at DESC LIMIT ? OFFSET ?",
            (*args, limit, offset),
        ).fetchall()
        items = [
            {
                "id": row[0],
                "session_id": row[1],
                "started_at": row[2],
                "duration_ms": round(row[3], 1),
                "outcome": row[4],
                "spans": row[5],
            }
            for row in rows
        ]
        return {"items": items, "total": total}

    def get(self, trace_id: str) -> RunTrace | None:
        row = self._conn.execute(
            "SELECT id, session_id, started_at, duration_ms, outcome "
            "FROM runs WHERE id = ?",
            (trace_id,),
        ).fetchone()
        if row is None:
            return None
        span_rows = self._conn.execute(
            "SELECT agent, event_type, latency_ms, error, reads, writes, llm_calls "
            "FROM spans WHERE run_id = ? ORDER BY id",
            (trace_id,),
        ).fetchall()
        spans = [
            AgentSpan(
                agent=r[0],
                event_type=r[1],
                latency_ms=r[2],
                error=r[3],
                reads=[ArtifactRef(**d) for d in json.loads(r[4])],
                writes=[ArtifactRef(**d) for d in json.loads(r[5])],
                llm_calls=[LLMCall(**d) for d in json.loads(r[6])],
            )
            for r in span_rows
        ]
        return RunTrace(
            id=row[0],
            session_id=row[1],
            started_at=datetime.fromtimestamp(row[2], tz=UTC),
            duration_ms=row[3],
            outcome=row[4],
            spans=spans,
        )
