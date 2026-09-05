"""ctxloom.testing — a scenario-testing harness for agent pipelines.

`ScenarioLab` is the entry point: seed some artifacts, run a set of agents,
assert on what happened (artifacts produced, tools called, agent path,
LLM usage, isolated errors). `lab.fail(...)` injects tool faults;
`lab.fail_resource(...)` injects a fault into any other resource (the LLM,
the embedder, a source); `mode=` on `ScenarioLab` switches the LLM between
live, record, and replay.
"""

from __future__ import annotations

from .assertions import (
    ArtifactAssertions,
    ErrorAssertions,
    LLMAssertions,
    PathAssertions,
    ToolAssertions,
)
from .exceptions import AssertionFailure, ScenarioError, ScenarioSkip
from .fault import ToolCallRecord, ToolCallRecorder, ToolFault
from .lab import Scenario, ScenarioLab, ScenarioResult
from .mock import ResourceFault
from .record import Mode, mode_from_env
from .registry import ScenarioCase, collect, scenario

__all__ = [
    "ArtifactAssertions",
    "AssertionFailure",
    "ErrorAssertions",
    "LLMAssertions",
    "Mode",
    "PathAssertions",
    "ResourceFault",
    "Scenario",
    "ScenarioCase",
    "ScenarioError",
    "ScenarioLab",
    "ScenarioResult",
    "ScenarioSkip",
    "ToolAssertions",
    "ToolCallRecord",
    "ToolCallRecorder",
    "ToolFault",
    "collect",
    "mode_from_env",
    "scenario",
]
