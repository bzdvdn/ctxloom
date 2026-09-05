"""Tool-level fault injection and call recording for `ctxloom.testing`.

ctxloom has no central tool registry — a `Tool` lives in a plain
`dict[str, Tool]` on whichever `ToolUse`/`ToolUseHITL` produce instance an
agent wires up (`ctxloom/tool_use.py`). To inject a fault (or just record
calls) for a tool by name, this module scans every agent's `produces` for
such a dict and wraps the matching `Tool.execute` in place, restoring the
original object afterward.

**Important caveat**: `_ToolLoopBase._run_tool` (`ctxloom/tool_use.py`)
catches any exception raised by `Tool.execute` and turns it into a plain text
string handed back to the LLM (`"Tool 'x' failed: ..."`) — it never
propagates out of the produce. So a fault injected via `lab.fail(...)` does
**not** abort the scenario run: the agent's LLM sees a tool-failure message
and may retry, give up, or answer anyway, exactly like a real transient tool
failure. `result.tools.called(name)` will show the failed call (`.error` set)
while `result.errors.none()` can still legitimately pass — the agent didn't
crash, it just saw an error and continued. Tools invoked directly from custom
`Produce` code (outside a `ToolUse` loop) are not affected by this
swallowing: an injected exception propagates normally there.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ctxloom.tools import Tool, ToolOutput

if TYPE_CHECKING:
    from ctxloom.agents import Agent


@dataclass
class ToolFault:
    """A queued fault for one tool name.

    `times=None` (default) raises on every call; `times=N` raises for the
    first `N` calls, then delegates to the real tool — the natural shape for
    testing "fails then recovers on retry" behavior.
    """

    tool_name: str
    error: BaseException | Callable[[], BaseException]
    times: int | None = None


@dataclass
class ToolCallRecord:
    """One recorded tool invocation, real or faulted."""

    tool: str
    args: dict[str, Any]
    output: ToolOutput | None
    error: str | None


class ToolCallRecorder:
    """Collects `ToolCallRecord`s. Installed on every run, fault or not."""

    def __init__(self) -> None:
        self.calls: list[ToolCallRecord] = []

    def record(
        self,
        tool: str,
        args: dict[str, Any],
        output: ToolOutput | None,
        error: str | None,
    ) -> None:
        self.calls.append(
            ToolCallRecord(tool=tool, args=args, output=output, error=error)
        )


def _iter_tool_dicts(agents: Sequence[Agent]) -> Iterator[dict[str, Tool]]:
    """Yields every `dict[str, Tool]`-shaped mapping found on any agent produce.

    Duck-typed (checks `.execute` on the values) rather than importing the
    private `_ToolLoopBase` class, so it keeps working if that internal is
    renamed or restructured.
    """
    for agent in agents:
        for produce_obj in getattr(agent, "produces", None) or []:
            tools = getattr(produce_obj, "tools", None)
            if (
                isinstance(tools, dict)
                and tools
                and all(hasattr(v, "execute") for v in tools.values())
            ):
                yield tools


class _WrappedTool(Tool):
    """Wraps one `Tool` instance: records every call, and raises `fault`'s
    error for its first `fault.times` calls (or forever, if `times=None`)."""

    def __init__(
        self, inner: Tool, fault: ToolFault | None, recorder: ToolCallRecorder
    ) -> None:
        self.name = inner.name
        self.description = inner.description
        self.destructive = inner.destructive
        self.schema = inner.schema
        self._inner = inner
        self._fault = fault
        self._remaining = fault.times if fault is not None else None
        self._recorder = recorder

    async def execute(self, args: dict[str, Any]) -> ToolOutput:
        fault = self._fault
        if fault is not None and (self._remaining is None or self._remaining > 0):
            if self._remaining is not None:
                self._remaining -= 1
            err = fault.error() if callable(fault.error) else fault.error
            self._recorder.record(self.name, args, None, str(err))
            raise err
        try:
            output = await self._inner.execute(args)
        except Exception as exc:
            self._recorder.record(self.name, args, None, str(exc))
            raise
        self._recorder.record(self.name, args, output, output.error or None)
        return output


def _wrap(tool: Tool, fault: ToolFault | None, recorder: ToolCallRecorder) -> Tool:
    return _WrappedTool(tool, fault, recorder)


class FaultInstaller:
    """Context manager: wraps matching tools for the duration of one run.

    Restores the exact original `Tool` objects in `__exit__`, even if the
    wrapped run raises.
    """

    def __init__(
        self,
        agents: Sequence[Agent],
        faults: list[ToolFault],
        recorder: ToolCallRecorder,
    ) -> None:
        self._agents = agents
        self._faults = {f.tool_name: f for f in faults}
        self._recorder = recorder
        self._originals: list[tuple[dict[str, Tool], str, Tool]] = []

    def __enter__(self) -> FaultInstaller:
        seen: set[int] = set()
        for tools in _iter_tool_dicts(self._agents):
            if id(tools) in seen:
                continue
            seen.add(id(tools))
            for name, tool in list(tools.items()):
                self._originals.append((tools, name, tool))
                tools[name] = _wrap(tool, self._faults.get(name), self._recorder)
        return self

    def __exit__(self, *exc: object) -> None:
        for tools, name, original in self._originals:
            tools[name] = original
        self._originals.clear()
