"""`ctxloom graph` — static agent blueprint from a module path."""

from __future__ import annotations

import argparse

from ..viz import blueprint
from .common import load_agents


def cmd_graph(args: argparse.Namespace) -> int:
    agents = load_agents(args.agents)
    print(blueprint(agents, title=args.title))
    return 0


def add_parser(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    p_graph = sub.add_parser("graph", help="static agent blueprint")
    p_graph.add_argument("agents", help='module path, e.g. "examples.knowledge.agents"')
    p_graph.add_argument("--title", default="ctxloom blueprint")
    p_graph.set_defaults(func=cmd_graph)
