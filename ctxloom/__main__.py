"""python -m ctxloom — inspect & visualize the runtime as Mermaid.

Subcommands:

    graph    static agent blueprint from a module path ("pkg.mod:Attr")
    context  live provenance graph from a saved session (KV backend)
    trace    run diagram from a trace store (SQLite)

Examples:

    python -m ctxloom graph examples.knowledge.agents:KnowledgeFlow
    python -m ctxloom context examples/knowledge/sessions/traces.sqlite3
    python -m ctxloom trace traces.db

Everything prints Mermaid source to stdout — paste it into GitHub, Notion or
mermaid.live.
"""

from __future__ import annotations

import argparse
import importlib
import sys
from typing import TYPE_CHECKING

from .agents import Agent
from .viz import blueprint, context_to_mermaid, trace_to_mermaid

if TYPE_CHECKING:
    from .checkpoints import FileKVBackend, SQLiteKVBackend


def _load_agents(spec: str) -> list[Agent]:
    module_name, has_attr, attr = spec.partition(":")
    module = importlib.import_module(module_name)
    if has_attr:
        obj = getattr(module, attr)
        if isinstance(obj, Agent):
            return [obj]
        if isinstance(obj, (list, tuple)):
            if not obj:
                raise SystemExit(f"{spec!r} resolved to an empty list")
            agents = [o for o in obj if isinstance(o, Agent)]
            if len(agents) != len(obj):
                raise SystemExit(
                    f"{spec!r} must resolve to an Agent or a list of Agents"
                )
            return agents
        raise SystemExit(f"expected an Agent or list[Agent] at {spec!r}")

    agents = [value for value in vars(module).values() if isinstance(value, Agent)]
    if not agents:
        # The demos instantiate their agents inline — synthesize the blueprint
        # from every Agent subclass defined in the module (stateless containers).
        classes = [
            value
            for name, value in sorted(vars(module).items())
            if isinstance(value, type)
            and issubclass(value, Agent)
            and value is not Agent
            and value.__module__ == module_name
        ]
        agents = [cls() for cls in classes]
    if not agents:
        raise SystemExit(
            f"no Agent instances or subclasses found in {module_name!r}; "
            'use the "module:Attr" form'
        )
    return agents


def _open_store(path: str, backend: str) -> FileKVBackend | SQLiteKVBackend:
    from .checkpoints import FileKVBackend, SQLiteKVBackend

    if backend == "sqlite" or path.endswith((".db", ".sqlite", ".sqlite3")):
        return SQLiteKVBackend(path)
    return FileKVBackend(path)


def cmd_graph(args: argparse.Namespace) -> int:
    agents = _load_agents(args.agents)
    print(blueprint(agents, title=args.title))
    return 0


def cmd_context(args: argparse.Namespace) -> int:
    from .session import SessionStore

    store = SessionStore(_open_store(args.path, args.backend))
    sessions = store.list_sessions()
    if not sessions:
        print("no sessions found")
        return 1
    session_id = args.session or sessions[-1]
    context = store.load_session(session_id)
    if context is None:
        print(f"session {session_id!r} not found")
        return 1
    print(context_to_mermaid(context, limit=args.limit))
    return 0


def cmd_trace(args: argparse.Namespace) -> int:
    from .tracing import TraceStore

    store = TraceStore(args.path)
    trace_id = args.run_id
    if trace_id is None:
        result = store.query(limit=1)
        if not result["items"]:
            print("no traces found")
            return 1
        trace_id = result["items"][0]["id"]
    trace = store.get(trace_id)
    if trace is None:
        print(f"trace {trace_id!r} not found")
        return 1
    print(trace_to_mermaid(trace))
    return 0


def cmd_replay(args: argparse.Namespace) -> int:
    from .replay import replay_context, replay_summary
    from .session import SessionStore

    store = SessionStore(_open_store(args.path, args.backend))
    sessions = store.list_sessions()
    if not sessions:
        print("no sessions found")
        return 1
    session_id = args.session or sessions[-1]
    try:
        context = replay_context(store, session_id, version=args.version)
    except KeyError as exc:
        print(str(exc))
        return 1
    summary = replay_summary(context)
    print(f"session {session_id!r} — replay v{summary['version']}")
    print(
        f"artifacts: {summary['artifacts']} · relations: {summary['relations']} · "
        f"pending questions: {summary['pending_questions']}"
    )
    for tname, count in sorted(summary["by_type"].items()):
        print(f"  {tname}: {count}")
    if args.diagram:
        from .viz import context_to_mermaid

        print()
        print(context_to_mermaid(context))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m ctxloom",
        description="Inspect & visualize ctxloom agents, contexts and traces as Mermaid.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_graph = sub.add_parser("graph", help="static agent blueprint")
    p_graph.add_argument(
        "agents", help='module path, e.g. "examples.knowledge.agents:KnowledgeFlow"'
    )
    p_graph.add_argument("--title", default="ctxloom blueprint")
    p_graph.set_defaults(func=cmd_graph)

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

    p_trace = sub.add_parser("trace", help="run diagram from a trace store")
    p_trace.add_argument("path", help="trace SQLite db")
    p_trace.add_argument(
        "run_id", nargs="?", default=None, help="run id (default: latest)"
    )
    p_trace.set_defaults(func=cmd_trace)

    p_replay = sub.add_parser(
        "replay", help="deterministic state replay of a saved session (§55)"
    )
    p_replay.add_argument(
        "path", help="KV backend file (sessions.sqlite3) or directory"
    )
    p_replay.add_argument(
        "--session", default=None, help="session id (default: latest)"
    )
    p_replay.add_argument(
        "--version", type=int, default=None, help="replay to this commit"
    )
    p_replay.add_argument("--backend", choices=["file", "sqlite"], default="auto")
    p_replay.add_argument(
        "--diagram", action="store_true", help="also print the provenance graph"
    )
    p_replay.set_defaults(func=cmd_replay)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
