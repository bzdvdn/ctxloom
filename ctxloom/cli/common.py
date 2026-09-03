"""Shared helpers for CLI subcommands: module-path agent loading, KV-backend
opening by path/extension. No argparse wiring here — see each subcommand
module for that."""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

from ..agents import Agent

if TYPE_CHECKING:
    from ..checkpoints import FileKVBackend, SQLiteKVBackend


def load_agents(spec: str) -> list[Agent]:
    module_name, has_attr, attr = spec.partition(":")
    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        raise SystemExit(
            f"could not import {module_name!r}: {exc}. If this is a local "
            "module (not installed as a package), run via "
            f"`uv run python -m ctxloom graph {spec}` instead."
        ) from exc
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
            for _name, value in sorted(vars(module).items())
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


def open_store(path: str, backend: str) -> FileKVBackend | SQLiteKVBackend:
    from ..checkpoints import FileKVBackend, SQLiteKVBackend

    if backend == "sqlite" or path.endswith((".db", ".sqlite", ".sqlite3")):
        return SQLiteKVBackend(path)
    return FileKVBackend(path)
