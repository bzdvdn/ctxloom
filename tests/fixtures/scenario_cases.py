"""Fixture scenarios for `tests/test_cli_scenario.py`.

Exercises every status the `ctxloom scenario` CLI can report (PASS/FAIL/
ERROR/SKIP) plus `--mode` plumbing through `mode_from_env()`, without
touching any real example, model, or network call.
"""

from __future__ import annotations

from ctxloom.testing import ScenarioSkip, mode_from_env, scenario

#: Set by `reports_mode()` below — read back by the test to confirm `--mode`
#: actually reached `CTXLOOM_SCENARIO_MODE` before this module's scenarios ran.
last_seen_mode: str | None = None


@scenario("fixture: passes")
async def passes() -> None:
    assert 1 + 1 == 2


@scenario("fixture: fails")
async def fails() -> None:
    assert 1 + 1 == 3, "math is broken"


@scenario("fixture: errors")
async def errors() -> None:
    raise RuntimeError("boom")


@scenario("fixture: skips")
async def skips() -> None:
    raise ScenarioSkip("no fixture configured")


@scenario("fixture: reports its mode")
async def reports_mode() -> None:
    global last_seen_mode
    last_seen_mode = mode_from_env()
