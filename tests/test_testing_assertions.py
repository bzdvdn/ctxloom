"""`ctxloom.testing.assertions` — the langgraph-scenario-lab-style sugar
methods (`contains`, `field_in`, `equals`, `PathAssertions.any_of`,
`ToolAssertions.called_any`), plus a smoke check on the pre-existing ones
they sit next to."""

from __future__ import annotations

import pytest
from ctxloom.context import Context
from ctxloom.testing.assertions import (
    ArtifactAssertions,
    PathAssertions,
    ToolAssertions,
)
from ctxloom.testing.exceptions import AssertionFailure
from ctxloom.testing.fault import ToolCallRecord
from pydantic import BaseModel


class Reply(BaseModel):
    text: str
    kind: str = "normal"


def _artifacts(*replies: Reply) -> ArtifactAssertions[Reply]:
    ctx = Context()
    for reply in replies:
        ctx.create(reply)
    return ArtifactAssertions(ctx, Reply)


def test_contains_passes_on_substring_match():
    a = _artifacts(Reply(text="the total is 3580 usd"))
    assert a.contains("3580").text == "the total is 3580 usd"


def test_contains_fails_with_actual_value_inlined():
    a = _artifacts(Reply(text="hello"))
    with pytest.raises(AssertionFailure, match="hello"):
        a.contains("3580")


def test_field_in_passes_when_value_is_one_of_the_options():
    a = _artifacts(Reply(text="hi", kind="greeting"))
    assert a.field_in("kind", ["greeting", "farewell"]).kind == "greeting"


def test_field_in_fails_when_value_is_not_in_the_options():
    a = _artifacts(Reply(text="hi", kind="greeting"))
    with pytest.raises(AssertionFailure, match="greeting"):
        a.field_in("kind", ["farewell"])


def test_equals_checks_every_field_at_once():
    a = _artifacts(Reply(text="hi", kind="greeting"))
    assert a.equals(text="hi", kind="greeting").text == "hi"


def test_equals_reports_every_mismatch():
    a = _artifacts(Reply(text="hi", kind="greeting"))
    with pytest.raises(AssertionFailure, match="kind"):
        a.equals(text="hi", kind="farewell")


def test_path_any_of_passes_when_one_agent_ran():
    from ctxloom.tracing.models import AgentSpan, RunTrace

    trace = RunTrace(
        id="t1",
        session_id="s1",
        outcome="completed",
        spans=[AgentSpan(agent="router")],
    )
    PathAssertions(trace).any_of("router", "planner")


def test_path_any_of_fails_when_none_ran():
    from ctxloom.tracing.models import AgentSpan, RunTrace

    trace = RunTrace(
        id="t1",
        session_id="s1",
        outcome="completed",
        spans=[AgentSpan(agent="router")],
    )
    with pytest.raises(AssertionFailure, match="router"):
        PathAssertions(trace).any_of("planner", "verifier")


def test_tool_called_any_returns_the_first_matching_call():
    calls = [
        ToolCallRecord(tool="search", args={}, output=None, error=None),
        ToolCallRecord(tool="calc", args={}, output=None, error=None),
    ]
    match = ToolAssertions(calls).called_any("calc", "fetch")
    assert match.tool == "calc"


def test_tool_called_any_fails_when_none_match():
    calls = [ToolCallRecord(tool="search", args={}, output=None, error=None)]
    with pytest.raises(AssertionFailure, match="search"):
        ToolAssertions(calls).called_any("calc", "fetch")
