"""`ctxloom branch` — persistent forks over a KV backend (§39-§40)."""

from __future__ import annotations

import argparse
import asyncio

from .common import open_store


async def _cmd_branch(args: argparse.Namespace) -> int:
    from ..branching import BranchStore
    from ..session import SessionStore

    store = SessionStore(open_store(args.path, args.backend))
    branches = BranchStore(store.backend)

    if args.action == "list":
        names = await branches.list_branches(args.session)
        stat = f"branches of {args.session!r}: " + (
            ", ".join(names) if names else "none"
        )
        print(stat)
        return 0

    if args.action == "save":
        context = await store.load_session(args.session)
        if context is None:
            print(f"session {args.session!r} not found")
            return 1
        await branches.save_branch(context, session_id=args.session, name=args.name)
        print(f"saved branch {args.session!r}:{args.name}")
        return 0

    # merge
    into = await branches.load_branch(args.session, args.into)
    source = await branches.load_branch(args.session, args.source)
    if into is None or source is None:
        print("missing branch (use 'branch list')")
        return 1
    try:
        into.merge(source)
    except Exception as exc:  # MergeConflict and friends
        print(str(exc))
        return 1
    if args.as_name:
        await branches.save_branch(into, session_id=args.session, name=args.as_name)
        print(f"merged into {args.session!r}:{args.as_name}")
    else:
        await branches.save_branch(into, session_id=args.session, name=args.into)
        print(f"merged {args.session!r}:{args.source} into {args.into}")
    return 0


def cmd_branch(args: argparse.Namespace) -> int:
    return asyncio.run(_cmd_branch(args))


def add_parser(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    p_branch = sub.add_parser(
        "branch", help="persistent forks over a KV backend (§39-§40)"
    )
    p_branch.add_argument(
        "path", help="KV backend file (sessions.sqlite3) or directory"
    )
    p_branch.add_argument("session", help="session id")
    p_branch.add_argument(
        "action", choices=["list", "save", "merge"], help="what to do"
    )
    p_branch.add_argument("name", nargs="?", default=None, help="name (save)")
    p_branch.add_argument("--into", default=None, help="merge target branch")
    p_branch.add_argument("--source", default=None, help="merge source branch")
    p_branch.add_argument(
        "--as", dest="as_name", default=None, help="result branch name"
    )
    p_branch.add_argument("--backend", choices=["file", "sqlite"], default="auto")
    p_branch.set_defaults(func=cmd_branch)
