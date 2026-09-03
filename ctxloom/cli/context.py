"""`ctxloom context` — live provenance graph from a saved session."""

from __future__ import annotations

import argparse
import asyncio

from .common import open_store


async def _cmd_context(args: argparse.Namespace) -> int:
    import sqlite3

    from ..session import SessionStore
    from ..viz import context_to_mermaid

    try:
        store = SessionStore(open_store(args.path, args.backend))
        sessions = await store.list_sessions()
    except sqlite3.OperationalError:
        print(f"no session store found at {args.path!r}")
        return 1
    if not sessions:
        print("no sessions found")
        return 1
    session_id = args.session or sessions[-1]
    context = await store.load_session(session_id)
    if context is None:
        print(f"session {session_id!r} not found")
        return 1
    print(context_to_mermaid(context, limit=args.limit))
    return 0


def cmd_context(args: argparse.Namespace) -> int:
    return asyncio.run(_cmd_context(args))


def add_parser(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    p_context = sub.add_parser(
        "context", help="live provenance graph of a saved session"
    )
    p_context.add_argument(
        "path", help="KV backend file (sessions.sqlite3) or directory"
    )
    p_context.add_argument(
        "--session", default=None, help="session id (default: latest)"
    )
    p_context.add_argument("--backend", choices=["file", "sqlite"], default="auto")
    p_context.add_argument(
        "--limit", type=int, default=None, help="max artifacts shown"
    )
    p_context.set_defaults(func=cmd_context)
