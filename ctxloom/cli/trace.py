"""`ctxloom trace` — run diagram from a trace store (SQLite)."""

from __future__ import annotations

import argparse


def cmd_trace(args: argparse.Namespace) -> int:
    import asyncio
    import sqlite3

    from ..tracing import TraceStore
    from ..viz import trace_to_mermaid

    store = TraceStore(args.path)

    async def _run() -> int:
        trace_id = args.run_id
        try:
            if trace_id is None:
                result = await store.query(limit=1)
                if not result["items"]:
                    print("no traces found")
                    return 1
                trace_id = result["items"][0]["id"]
            trace = await store.get(trace_id)
        except sqlite3.OperationalError:
            print(f"no trace store found at {args.path!r}")
            return 1
        if trace is None:
            print(f"trace {trace_id!r} not found")
            return 1
        print(trace_to_mermaid(trace))
        return 0

    return asyncio.run(_run())


def add_parser(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    p_trace = sub.add_parser("trace", help="run diagram from a trace store")
    p_trace.add_argument("path", help="trace SQLite db")
    p_trace.add_argument(
        "run_id", nargs="?", default=None, help="run id (default: latest)"
    )
    p_trace.set_defaults(func=cmd_trace)
