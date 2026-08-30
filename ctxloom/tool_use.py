"""Tool-use for LLM agents: \"LLM decides → tool → … → answer\" as a Produce.

Two loop variants:
- `ToolUse` — a blocking loop in a single produce (simple, atomic);
- `ToolUseHITL` — reactive, step by step: can ask the human clarifying
  questions (`type:\"ask\"` → `PendingQuestion`) and resume after the answer
  (§60). Intermediate steps are state (`Observation`).

Both end in a `ToolAnswer` artifact (the LLM final answer, §68); your produces
turn it into domain artifacts. `ToolAnswer.agent` distinguishes answers from
different LLM agents in one Runtime.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from typing import Any, Literal

from pydantic import BaseModel, Field

from .artifacts import Artifact
from .context import Context
from .events import Event
from .interrupt import PendingQuestion
from .produce import Produce
from .structured import structured_llm
from .tools import Tool


class ToolAnswer(BaseModel):
    """Final LLM answer as an artifact (§68). `agent` — which ToolUse created it."""

    agent: str = ""
    query_id: str = ""
    text: str = ""


class Observation(BaseModel):
    """A step in the reactive loop: a tool result (tool) or a human answer (user)."""

    query_id: str
    text: str
    step: int = 0
    source: str = "tool"
    agent: str = ""


class _ToolUseStep(BaseModel):
    """LLM decision inside the blocking loop: call a tool or answer."""

    type: Literal["tool_call", "answer"]
    tool: str = ""
    args: dict[str, Any] = Field(default_factory=dict)
    text: str = ""


class _ToolUseStepHITL(BaseModel):
    """LLM decision inside the reactive loop: tool / clarify / answer."""

    type: Literal["tool_call", "answer", "ask"]
    tool: str = ""
    args: dict[str, Any] = Field(default_factory=dict)
    text: str = ""


class _FinalAnswer(BaseModel):
    """Forced answer when the loop hit the step limit."""

    text: str = ""


class ToolUse(Produce[ToolAnswer]):
    """Blocking loop \"LLM decides → tool → … → answer\" in a single produce.

    Simple, no HITL: the LLM either calls a tool or answers. The logic lives here,
    not in the container agent. Destructive tools are not offered to the LLM.
    """

    artifact_type = ToolAnswer

    def __init__(
        self,
        system: str,
        tools: Sequence[Tool] | dict[str, Tool],
        *,
        name: str = "llm",
        max_steps: int = 8,
    ):
        self.name = name
        self.system = system
        self.tools = (
            {t.name: t for t in tools} if not isinstance(tools, dict) else dict(tools)
        )
        self.max_steps = max_steps
        super().__init__()

    async def produce(
        self,
        context: Context,
        inputs: list[Artifact[Any]],
        event: Event | None = None,
    ) -> None:
        artifact = context.get(event.artifact_id) if event is not None else None
        if artifact is None or isinstance(artifact.data, ToolAnswer):
            return None  # final answer is handled by user produces
        goal = getattr(artifact.data, "text", "") or ""
        text = await self._loop(context, goal)
        self.effects.create(
            ToolAnswer(agent=self.name, query_id=artifact.id, text=text)
        )
        return None

    async def _loop(self, context: Context, goal: str) -> str:
        history: list[str] = []
        budget = context.resources.get("budget")
        max_tool_calls = budget.max_tool_calls if budget is not None else None
        executed = 0
        context.announce("Deciding next action…", kind="agent", agent=self.name)
        for _ in range(self.max_steps):
            decision = await structured_llm(
                context,
                schema=_ToolUseStep,
                system=self._system_prompt(),
                user=self._user_prompt(goal, history),
            )
            if decision is None:
                return "Could not reach a decision."
            if decision.type == "answer":
                return decision.text
            if not decision.tool:
                return "Tool not specified."
            if max_tool_calls is not None and executed >= max_tool_calls:
                history.append(
                    "Tool budget exhausted; answer based on the available data."
                )
                continue
            context.announce(
                f"Calling tool '{decision.tool}'…", kind="agent", tool=decision.tool
            )
            result = await self._run_tool(context, decision.tool, decision.args)
            executed += 1
            history.append(
                f"tool_call: {decision.tool}({json.dumps(decision.args, ensure_ascii=False)})\n"
                f"result: {result}"
            )
        # Loop hit the limit: force the LLM to answer based on the data.
        forced = await structured_llm(
            context,
            schema=_FinalAnswer,
            system="Answer now based on the available data. "
            'Reply with strict JSON: {"text":"..."}',
            user=self._user_prompt(goal, history),
        )
        if forced is not None and forced.text:
            return forced.text
        return "Step limit reached; answer based on the available data."

    def _system_prompt(self) -> str:
        usable = [t for t in self.tools.values() if not t.destructive]
        schemas = "\n".join(
            f"- {t.name}: {t.description}\n  args: {json.dumps(t.schema, ensure_ascii=False)}"
            for t in usable
        )
        return (
            f"{self.system}\n\n"
            f"Available tools:\n{schemas}\n\n"
            "You work in a loop, one step at a time. Each step reply with strict "
            "JSON matching this schema: "
            '{"type":"tool_call","tool":"<name>","args":{...}} — call a tool, or '
            '{"type":"answer","text":"..."} — final answer.\n'
            "Rules:\n"
            "- Call at most one tool per step, and never call the same tool twice "
            "in a row.\n"
            "- After a tool result, give the final answer on the next step, unless "
            "the result is clearly insufficient.\n"
            "- Call a tool only when you lack the information; finish within at "
            "most 3 tool calls — prefer answering over extra calls."
        )

    @staticmethod
    def _user_prompt(goal: str, history: list[str]) -> str:
        results = "\n\n".join(history)
        return f"Goal: {goal}\n\nTool results so far:\n{results or '—'}"

    async def _run_tool(
        self, context: Context, tool_id: str, args: dict[str, Any]
    ) -> str:
        tool = self.tools.get(tool_id)
        if tool is None:
            available = ", ".join(self.tools)
            return f"Unknown tool '{tool_id}'. Available: {available}"
        if tool.destructive:
            return f"Tool '{tool_id}' is destructive and not offered to the LLM."
        try:
            output = await tool.execute(args)
        except Exception as exc:  # noqa: BLE001 — tool failure is returned to the LLM
            return f"Tool '{tool_id}' failed: {exc}"
        if output.error:
            return output.error
        return (
            output.text if output.text else json.dumps(output.data, ensure_ascii=False)
        )


class ToolUseHITL(Produce[ToolAnswer]):
    """Reactive loop: step by step, can ask the human (HITL, §60).

    The LLM may answer (`answer`), call a tool (`tool_call`, result goes into an
    `Observation`), or ask a clarifying question (`ask` → `PendingQuestion`).
    The human answer comes back into the loop as `Observation(source="user")`.
    """

    artifact_type = ToolAnswer

    def __init__(
        self,
        system: str,
        tools: Sequence[Tool] | dict[str, Tool],
        *,
        name: str = "llm",
        max_steps: int = 8,
        max_asks: int = 2,
        resume_announce: Callable[[str], str] | None = None,
    ):
        self.name = name
        self.system = system
        self.tools = (
            {t.name: t for t in tools} if not isinstance(tools, dict) else dict(tools)
        )
        self.max_steps = max_steps
        self.max_asks = max_asks
        # App callback: human answer → status message (kind="status").
        self.resume_announce = resume_announce
        super().__init__()

    async def produce(
        self,
        context: Context,
        inputs: list[Artifact[Any]],
        event: Event | None = None,
    ) -> None:
        resolved = self._resolve(context, event)
        if resolved is None:
            return None
        qid, kind, extra = resolved
        goal = self._goal(context, qid)
        history = self._history(context, qid)

        if kind == "resume":
            # human answer to a clarify → user observation, continue.
            # Status from the app (kind="status"): text authored by the app.
            if self.resume_announce is not None:
                context.announce(
                    self.resume_announce(extra), kind="status", agent=self.name
                )
            self.effects.create(
                Observation(
                    query_id=qid,
                    step=len(history) + 1,
                    text=extra,
                    source="user",
                    agent=self.name,
                )
            )
            return None

        if len(history) >= self.max_steps:
            await self._forced_answer(context, qid, goal, history)
            return None

        decision = await structured_llm(
            context,
            schema=_ToolUseStepHITL,
            system=self._system_prompt(),
            user=self._user_prompt(goal, history),
        )
        if decision is None:
            self._answer(qid, "Could not reach a decision.")
            return None
        if decision.type == "answer":
            self._answer(qid, decision.text)
            return None
        if decision.type == "ask":
            if not decision.text:
                self._answer(qid, "Question not specified.")
                return None
            asked = [
                q
                for q in context.list_artifacts(PendingQuestion)
                if q.data.notes.get("query_id") == qid
                and q.data.question == decision.text
            ]
            if asked:
                answers = [q.data.resolution for q in asked if q.data.answered]
                if not answers:
                    # the same question was already asked and awaits an answer
                    return None
                # LLM asks the same thing again — nudge it to continue
                self.effects.create(
                    Observation(
                        query_id=qid,
                        step=len(history) + 1,
                        text=(
                            f"You already asked '{decision.text}' and the user "
                            f"answered: {answers[-1]}. Use that answer and "
                            "proceed to a final answer."
                        ),
                        source="tool",
                        agent=self.name,
                    )
                )
                return None
            asked_count = len(
                [
                    q
                    for q in context.list_artifacts(PendingQuestion)
                    if q.data.notes.get("query_id") == qid
                ]
            )
            if asked_count >= self.max_asks:
                # no more questions — continue with what we have
                self.effects.create(
                    Observation(
                        query_id=qid,
                        step=len(history) + 1,
                        text=(
                            "You have already asked enough clarifying questions. "
                            "Proceed with the tool call using the available values; "
                            "if a value is missing, use a reasonable default and "
                            "note it in the final answer."
                        ),
                        source="tool",
                        agent=self.name,
                    )
                )
                return None
            self.effects.ask(
                decision.text,
                kind="clarify",
                notes={"query_id": qid, "agent": self.name},
            )
            return None
        if not decision.tool:
            self._answer(qid, "Tool not specified.")
            return None

        tool_history = [o for o in history if o.source == "tool"]
        budget = context.resources.get("budget")
        max_tool_calls = budget.max_tool_calls if budget is not None else None
        if max_tool_calls is not None and len(tool_history) >= max_tool_calls:
            self.effects.create(
                Observation(
                    query_id=qid,
                    step=len(history) + 1,
                    text=(
                        f"Tool budget ({max_tool_calls}) exhausted; "
                        "answer based on the available data."
                    ),
                    source="tool",
                    agent=self.name,
                )
            )
            return None
        context.announce(
            f"Calling tool '{decision.tool}'…", kind="agent", tool=decision.tool
        )
        result = await self._run_tool(context, decision.tool, decision.args)
        self.effects.create(
            Observation(
                query_id=qid,
                step=len(history) + 1,
                text=result,
                source="tool",
                agent=self.name,
            )
        )
        return None

    def _answer(self, qid: str, text: str) -> None:
        self.effects.create(ToolAnswer(agent=self.name, query_id=qid, text=text))

    def _resolve(
        self, context: Context, event: Event | None
    ) -> tuple[str, str, str] | None:
        """(query_id, kind, extra): start / continue / resume (human answer)."""
        artifact = context.get(event.artifact_id) if event is not None else None
        if artifact is None:
            return None
        data = artifact.data
        if isinstance(data, Observation):
            return data.query_id, "continue", ""
        if isinstance(data, PendingQuestion):
            if not data.answered:
                return None  # waiting for the human answer
            qid = data.notes.get("query_id")
            if not qid:
                return None
            return qid, "resume", data.resolution or ""
        if isinstance(data, ToolAnswer):
            return None  # final answer is handled by user produces
        return artifact.id, "start", ""

    @staticmethod
    def _goal(context: Context, qid: str) -> str:
        artifact = context.get(qid)
        if artifact is None:
            return ""
        return getattr(artifact.data, "text", "") or ""

    @staticmethod
    def _history(context: Context, qid: str) -> list[Observation]:
        observations = [
            o for o in context.list_artifacts(Observation) if o.data.query_id == qid
        ]
        observations.sort(key=lambda o: o.data.step)
        return [o.data for o in observations]

    async def _forced_answer(
        self, context: Context, qid: str, goal: str, history: list[Observation]
    ) -> None:
        forced = await structured_llm(
            context,
            schema=_FinalAnswer,
            system="Answer now based on the available data. "
            'Reply with strict JSON: {"text":"..."}',
            user=self._user_prompt(goal, history),
        )
        text = (
            forced.text
            if forced is not None and forced.text
            else "Step limit reached; answer based on the available data."
        )
        self._answer(qid, text)

    def _system_prompt(self) -> str:
        usable = [t for t in self.tools.values() if not t.destructive]
        schemas = "\n".join(
            f"- {t.name}: {t.description}\n  args: {json.dumps(t.schema, ensure_ascii=False)}"
            for t in usable
        )
        return (
            f"{self.system}\n\n"
            f"Available tools:\n{schemas}\n\n"
            "You work in a loop, one step at a time. Each step reply with strict "
            "JSON matching this schema: "
            '{"type":"tool_call","tool":"<name>","args":{...}} — call a tool, '
            '{"type":"ask","text":"..."} — ask the user a clarifying question, or '
            '{"type":"answer","text":"..."} — final answer.\n'
            "Rules:\n"
            "- If you lack context a tool needs (e.g. namespace, repository, role), "
            "ask the user via type:ask — never guess or invent it.\n"
            "- Ask at most one question per missing value, and NEVER ask for the "
            "same value twice. Once the user answers, use that answer as-is and "
            "continue with the tool call — proceed even if the answer is short or "
            "unusual.\n"
            "- Call at most one tool per step, and never call the same tool twice "
            "in a row.\n"
            "- After a tool result, give the final answer on the next step, unless "
            "the result is clearly insufficient.\n"
            "- Call a tool only when you lack the information; finish within at "
            "most 3 tool calls — prefer answering over extra calls."
        )

    @staticmethod
    def _user_prompt(goal: str, history: list[Observation]) -> str:
        parts = [
            f"user answer: {o.text}" if o.source == "user" else f"tool result: {o.text}"
            for o in history
        ]
        return f"Goal: {goal}\n\nContext so far:\n" + ("\n".join(parts) or "—")

    async def _run_tool(
        self, context: Context, tool_id: str, args: dict[str, Any]
    ) -> str:
        tool = self.tools.get(tool_id)
        if tool is None:
            available = ", ".join(self.tools)
            return f"Unknown tool '{tool_id}'. Available: {available}"
        if tool.destructive:
            return f"Tool '{tool_id}' is destructive and not offered to the LLM."
        try:
            output = await tool.execute(args)
        except Exception as exc:  # noqa: BLE001 — tool failure is returned to the LLM
            return f"Tool '{tool_id}' failed: {exc}"
        if output.error:
            return output.error
        return (
            output.text if output.text else json.dumps(output.data, ensure_ascii=False)
        )
