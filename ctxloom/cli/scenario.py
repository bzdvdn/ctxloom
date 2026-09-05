"""`ctxloom scenario` — run `ctxloom.testing` scenarios.

A separate track from `pytest`: scenarios are `@scenario`-decorated functions
(usually wrapping `ScenarioLab.run()`) living in ordinary modules, imported by
dotted path exactly like `ctxloom graph <module:Attr>` resolves agents — no
`test_*.py` naming, no pytest collection, so a plain `pytest` run never needs a
model key or a network connection. Point this at one or more modules and it
imports them, runs whatever they registered, and reports PASS/FAIL/SKIP.
"""

from __future__ import annotations

import argparse
import asyncio
import inspect
import os
import time

from ..testing.exceptions import ScenarioSkip
from ..testing.record import MODE_ENV_VAR
from ..testing.registry import ScenarioCase, collect


async def _run_one(case: ScenarioCase) -> tuple[str, str]:
    """Returns `(status, detail)` — status is one of PASS/FAIL/ERROR/SKIP."""
    try:
        result = case.func()
        if inspect.isawaitable(result):
            await result
    except ScenarioSkip as exc:
        return "SKIP", str(exc)
    except AssertionError as exc:
        return "FAIL", str(exc)
    except Exception as exc:  # noqa: BLE001 — report, don't crash the run
        return "ERROR", f"{type(exc).__name__}: {exc}"
    return "PASS", ""


def cmd_scenario(args: argparse.Namespace) -> int:
    if args.mode is not None:
        os.environ[MODE_ENV_VAR] = args.mode

    cases = collect(args.modules)
    if args.filter:
        cases = [c for c in cases if args.filter in c.name]
    if not cases:
        print("no scenarios found (check the module path and -k filter)")
        return 1

    counts = {"PASS": 0, "FAIL": 0, "ERROR": 0, "SKIP": 0}
    for case in cases:
        started = time.monotonic()
        status, detail = asyncio.run(_run_one(case))
        elapsed = time.monotonic() - started
        counts[status] += 1
        line = f"{status:<5} {case.name} ({elapsed:.2f}s)"
        print(line)
        if detail:
            print(f"      {detail}")

    total = len(cases)
    print(
        f"\n{total} scenario(s): {counts['PASS']} passed, {counts['FAIL']} failed, "
        f"{counts['ERROR']} errored, {counts['SKIP']} skipped"
    )
    return 1 if counts["FAIL"] or counts["ERROR"] else 0


def add_parser(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    p_scenario = sub.add_parser(
        "scenario", help="run ctxloom.testing scenarios (separate from pytest)"
    )
    p_scenario.add_argument(
        "modules",
        nargs="+",
        help='dotted module path(s) to import, e.g. "examples.repair.scenarios"',
    )
    p_scenario.add_argument(
        "-k",
        "--filter",
        default=None,
        help="only run scenarios whose name contains this substring",
    )
    p_scenario.add_argument(
        "--mode",
        choices=["live", "record", "replay"],
        default=None,
        help=(
            "sets CTXLOOM_SCENARIO_MODE for scenarios built with "
            "ctxloom.testing.mode_from_env() — most scenarios default to "
            "'live' or opt out entirely without it"
        ),
    )
    p_scenario.set_defaults(func=cmd_scenario)
