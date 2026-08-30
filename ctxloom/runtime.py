import asyncio
import json
import time
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

from .agents import Agent
from .budget import Budget, RunOutcome, RunStats
from .commit import Commit, Read, Write
from .context import Context
from .effects import Effects, current_effects, reset_effects, set_effects
from .events import Event
from .patches import Create, Delete, Link, Patch, Unlink, Update
from .session import Session
from .streaming import ProgressEvent
from .tracing.models import AgentSpan, ArtifactRef, LLMCall, RelationRef, RunTrace
from .tracing.tracer import CompositeTracer, RecordingLLM, Tracer, _clip

#: A scheduled patch with its trigger reads and (optional) trace span.
PatchWork = tuple[Patch, Agent, list[Read], AgentSpan | None]


class Runtime:
    def __init__(
        self,
        context: Context,
        agents: list[Agent] | None = None,
        max_concurrency: int | None = None,
        session: "Session | None" = None,
        budget: Budget | None = None,
        tracer: Tracer | list[Tracer] | None = None,
    ):
        self.context = context
        self.agents = agents or []
        self.max_concurrency = max_concurrency
        self.session = session
        self.budget = budget
        self.tracer: Tracer | CompositeTracer | None = (
            tracer
            if isinstance(tracer, Tracer) or tracer is None
            else CompositeTracer(tracer)
        )
        # Tracing LLM calls: task → agent, accumulated LLMCall's.
        self._agent_by_task: dict[asyncio.Task[Any], str] = {}
        self._pending_llm: dict[str, list[LLMCall]] = {}
        if self.tracer is not None and context.resources.llm is not None:
            context.resources.llm = RecordingLLM(
                context.resources.llm,
                on_call=self._record_llm,
                agent_of=self._current_agent_name,
            )
        self.outcome: RunOutcome = RunOutcome.COMPLETED
        self.last_stats: RunStats | None = None
        self._runs_used = 0
        self._deadline: float | None = None
        self._active_budget: Budget | None = None
        self._turn_started = False
        self._turn_started_at = 0.0
        self._run_id = ""
        self._spans: list[AgentSpan] = []
        # Memo: (artifact_id, version) → serialized data for one turn.
        self._trace_data_cache: dict[tuple[str, int], str] = {}

    def register(self, agent: Agent) -> None:
        self.agents.append(agent)

    def _current_agent_name(self) -> str:
        task = asyncio.current_task()
        if task is None:
            return ""
        return self._agent_by_task.get(task, "")

    def _record_llm(self, call: LLMCall) -> None:
        self._pending_llm.setdefault(call.agent, []).append(call)

    def _artifact_ref(
        self,
        artifact_id: str,
        version: int,
        op_type: str,
        model: Any | None,
    ) -> ArtifactRef:
        data: str | None = None
        if model is not None:
            key = (artifact_id, version)
            data = self._trace_data_cache.get(key)
            if data is None:
                data = _clip(
                    json.dumps(model.model_dump(mode="json"), ensure_ascii=False)
                )
                self._trace_data_cache[key] = data
        return ArtifactRef(
            artifact_id=artifact_id,
            version=version,
            op_type=op_type,
            data_type=type(model).__name__ if model is not None else "",
            data=data,
        )

    def _artifact_data(self, artifact_id: str) -> Any | None:
        artifact = self.context.get(artifact_id)
        return artifact.data if artifact is not None else None

    @staticmethod
    def _type_name(artifact_id: str, context: Context | None) -> str:
        artifact = context.get(artifact_id) if context is not None else None
        data = artifact.data if artifact is not None else None
        return type(data).__name__ if data is not None else ""

    def _relation_refs(self, patch: Patch) -> list[RelationRef]:
        """Provenance edges (`patch.link`) recorded for the span (§34)."""
        refs: list[RelationRef] = []
        for op in patch.operations:
            if not isinstance(op, Link):
                continue
            refs.append(
                RelationRef(
                    source_id=op.artifact_id,
                    relation=op.relation,
                    target_id=op.target_id,
                    source_type=self._type_name(op.artifact_id, self.context),
                    target_type=self._type_name(op.target_id, self.context),
                )
            )
        return refs

    def _write_refs(self, patch: Patch, writes: list[Write]) -> list[ArtifactRef]:
        ops_by_id: dict[str, tuple[str, Any | None]] = {}
        for op in patch.operations:
            artifact_id = getattr(op, "artifact_id", None)
            if artifact_id is None:
                continue
            if isinstance(op, Create):
                model: Any | None = op.data
            elif isinstance(op, Update):
                model = op.new_data
            else:
                model = None
            ops_by_id[artifact_id] = (op.to_dict().get("type", ""), model)
        return [
            self._artifact_ref(
                w.artifact_id,
                w.version,
                ops_by_id.get(w.artifact_id, ("", None))[0],
                ops_by_id.get(w.artifact_id, ("", None))[1],
            )
            for w in writes
        ]

    def _begin_turn(self, budget: Budget | None) -> None:
        self._runs_used = 0
        self.outcome = RunOutcome.COMPLETED
        self._deadline = None
        self._turn_started_at = time.monotonic()
        self._active_budget = budget or self.budget
        # expose budget visibility to agents (LLM agent counts max_tool_calls)
        self.context.resources.set("budget", self._active_budget)
        if (
            self._active_budget is not None
            and self._active_budget.max_seconds is not None
        ):
            self._deadline = self._turn_started_at + self._active_budget.max_seconds
        self._turn_started = True

        # trace of the current run (§54): only if the tracer is enabled
        if self.tracer is not None:
            self._run_id = str(uuid.uuid4())
            self._spans = []
            self._trace_data_cache = {}
            self.tracer.on_turn_begin(
                self._run_id,
                session_id=self.session.session_id if self.session is not None else "",
                started_at=datetime.now(UTC),
            )

    def _budget_exhausted(self) -> bool:
        if self._deadline is not None and time.monotonic() >= self._deadline:
            self.outcome = RunOutcome.BUDGET_TIME_EXCEEDED
            return True
        if (
            self._active_budget is not None
            and self._active_budget.max_runs is not None
            and self._runs_used >= self._active_budget.max_runs
        ):
            self.outcome = RunOutcome.BUDGET_RUNS_EXCEEDED
            return True
        return False

    def _validate_patch_types(self, patch: Patch, agent: Agent) -> None:
        """Checks that all Create operations match the agent's produces."""
        if agent.produces is None:
            return  # no restrictions
        allowed_types = {
            p.artifact_type for p in agent.produces if p.artifact_type is not None
        }
        if not allowed_types:
            return
        for op in patch.operations:
            if isinstance(op, Create) and type(op.data) not in allowed_types:
                raise ValueError(
                    f"Agent '{agent.name}' created artifact of type {type(op.data).__name__}, "
                    f"which is not declared in produces: {[t.__name__ for t in allowed_types]}"
                )

    async def arun_once(self, budget: Budget | None = None) -> int:
        if not self._turn_started:
            self._begin_turn(budget)
        events = self.context.drain_events()
        if not events:
            return 0
        if self._budget_exhausted():
            return 0

        # Collect work (event, agent), accounting for priority: agents with lower
        # values run earlier, "finishers" last.
        work: list[tuple[Agent, Event, list[Read]]] = []
        ordered_agents = sorted(self.agents, key=lambda a: a.priority)
        for event in events:
            if self._budget_exhausted():
                break
            for agent in ordered_agents:
                if self._budget_exhausted():
                    break
                if agent.matches(event, self.context):
                    reads = self._collect_reads(agent, event)
                    work.append((agent, event, reads))

        # Limit the number of runs by the max_runs budget. Set the budget_runs_exceeded
        # outcome only when the limit is actually reached, not when the event simply
        # has no subscribed agents.
        active = self._active_budget
        if active is not None and active.max_runs is not None:
            remaining = active.max_runs - self._runs_used
            if remaining <= 0:
                self.outcome = RunOutcome.BUDGET_RUNS_EXCEEDED
                work = []
            else:
                work = work[:remaining]

        results = await self._dispatch(work)
        patches_to_apply, runs = self._get_patches_to_apply(results)
        self._commit_patches_to_apply(patches_to_apply)
        return runs

    async def _dispatch(self, work: list[tuple[Agent, Event, list[Read]]]) -> list[Any]:
        """Runs the generation's workers.

        Sequential when there is nothing to parallelize (no runtime cap and no
        per-agent limits); otherwise concurrent with: the global
        `max_concurrency` cap plus per-agent `concurrency_limit` tiers — so
        LLM-bound producers can be throttled separately from cheap I/O.
        Semaphores are acquired global-first (fixed order avoids deadlocks) and
        released in reverse.
        """
        if not work:
            return []
        limiters = {
            agent.concurrency_limit
            for agent, _, _ in work
            if agent.concurrency_limit is not None and agent.concurrency_limit > 0
        }
        if self.max_concurrency is None and not limiters:
            return [await self._execute(item) for item in work]

        global_semaphore = (
            asyncio.Semaphore(self.max_concurrency)
            if self.max_concurrency is not None
            else None
        )
        limit_semaphores = {limit: asyncio.Semaphore(limit) for limit in limiters}

        async def _worker(item: tuple[Agent, Event, list[Read]]) -> Any:
            agent = item[0]
            acquired: list[asyncio.Semaphore] = []
            tier = agent.concurrency_limit
            if tier is not None and tier > 0:
                acquired.append(limit_semaphores[tier])
            if global_semaphore is not None:
                acquired.append(global_semaphore)
            for semaphore in acquired:
                await semaphore.acquire()
            try:
                return await self._execute(item, None)
            finally:
                for semaphore in reversed(acquired):
                    semaphore.release()

        return await asyncio.gather(*(_worker(item) for item in work))

    def _get_patches_to_apply(self, results: list[Any]) -> tuple[list[PatchWork], int]:
        """Turns agent results into the patches to apply (+ the run count).

        Executions that changed nothing are not applied and not traced (a
        monotonic flood of "checked, no work" spans would make traces
        unreadable, §54), but they still count toward the run budget.
        """
        patches_to_apply: list[PatchWork] = []
        runs = 0
        for patch, agent, event, reads, latency in results:
            if self._budget_exhausted():
                break
            runs += 1
            self._runs_used += 1
            if patch is None or patch.is_empty():
                continue
            span: AgentSpan | None = None
            if self.tracer is not None:
                read_refs = [
                    self._artifact_ref(
                        read.artifact_id,
                        read.version,
                        "read",
                        self._artifact_data(read.artifact_id),
                    )
                    for read in reads
                ]
                span = AgentSpan(
                    agent=agent.name,
                    event_type=event.type.value,
                    reads=read_refs,
                    latency_ms=latency,
                    llm_calls=self._pending_llm.pop(agent.name, []),
                    started_at=datetime.now(UTC),
                )
                self._spans.append(span)
                self.tracer.on_span(span)
            self._validate_patch_types(patch, agent)
            patches_to_apply.append((patch, agent, reads, span))
        return patches_to_apply, runs

    def _commit_patches_to_apply(self, patches_to_apply: list[PatchWork]) -> None:
        """Applies each patch as a commit: provenance, span writes, persistence."""
        for patch, agent, reads, span in patches_to_apply:
            commit = Commit(
                author=agent.name,
                message=f"Applied patch from agent '{agent.name}'",
                operations=patch.operations,
                reads=reads,
            )
            commit.writes = self._apply_patch(patch, commit)
            if span is not None:
                span.writes = self._write_refs(patch, commit.writes)
                span.relations = self._relation_refs(patch)
            self.context.log_commit(commit)
            if self.session is not None:
                # git-like persist after each commit: the session survives a crash
                # at the boundary of any agent generation
                self.session.save()

    def _collect_reads(self, agent: Agent, event: Event) -> list[Read]:
        """Records consumed artifacts: the trigger event + inputs per consumes.

        This is the actual link of an agent to its ancestors (git-like provenance),
        built by the runtime rather than by the graph author.
        """
        reads: list[Read] = []
        seen: set[str] = set()
        trigger_artifact = self.context.get(event.artifact_id)
        if trigger_artifact is not None:
            reads.append(Read(trigger_artifact.id, trigger_artifact.version))
            seen.add(trigger_artifact.id)
        for artifact in agent.collect_inputs(self.context):
            if artifact.id not in seen:
                reads.append(Read(artifact.id, artifact.version))
                seen.add(artifact.id)
        return reads

    async def _execute(
        self,
        item: tuple[Agent, Event, list[Read]],
        semaphore: asyncio.Semaphore | None = None,
    ) -> tuple[Patch | None, Agent, Event, list[Read], float]:
        """Runs a single agent (parallel section of a generation).

        Agents in the same generation work on the same snapshot:
        patches are applied only after all runs finish, so a parallel
        fan-out is safe for provenance (§42, §34).
        """
        agent, event, reads = item
        started = time.monotonic()
        task = asyncio.current_task()
        if task is not None:
            self._agent_by_task[task] = agent.name
        effects_token = set_effects(Effects(self.context))
        slot: Effects | None = None
        try:
            if semaphore is not None:
                async with semaphore:
                    patch = await agent.run(event, self.context)
            else:
                patch = await agent.run(event, self.context)
            slot = current_effects()
        finally:
            reset_effects(effects_token)
            if task is not None and task in self._agent_by_task:
                del self._agent_by_task[task]
        # Effects authored in produce() compile to the patch. A produce's own
        # effects happen *after* its returned patch (produce order), so an
        # update that captured the pre-effect state cannot regress later effects.
        if slot is not None and not slot.is_empty():
            combined = Patch()
            if patch is not None:
                combined.merge(patch)
            combined.merge(slot.to_patch())
            patch = combined
        return patch, agent, event, reads, (time.monotonic() - started) * 1000

    async def arun(
        self,
        max_iterations: int = 100,
        budget: Budget | None = None,
    ) -> int:
        self._begin_turn(budget)
        active = self._active_budget
        limit = (
            active.max_iterations
            if active is not None and active.max_iterations is not None
            else max_iterations
        )
        total_runs = 0
        for _ in range(limit):
            if self._budget_exhausted():
                break
            runs = await self.arun_once()
            total_runs += runs
            if runs == 0:
                break
        else:
            if self.outcome == RunOutcome.COMPLETED:
                self.outcome = RunOutcome.ITERATIONS_EXHAUSTED
        self.last_stats = RunStats(
            runs=total_runs,
            iterations=limit,
            outcome=self.outcome,
            duration=time.monotonic() - self._turn_started_at,
        )
        if self.tracer is not None:
            self.tracer.on_turn_end(
                RunTrace(
                    id=self._run_id,
                    session_id=(
                        self.session.session_id if self.session is not None else ""
                    ),
                    started_at=datetime.now(UTC),
                    duration_ms=time.monotonic() - self._turn_started_at,
                    outcome=self.outcome.value,
                    spans=self._spans,
                )
            )
        return total_runs

    def run_once(self) -> int:
        return asyncio.run(self.arun_once())

    def run(self, max_iterations: int = 100, budget: Budget | None = None) -> int:
        return asyncio.run(self.arun(max_iterations, budget))

    async def astream(
        self,
        budget: Budget | None = None,
        max_iterations: int = 1000,
    ) -> AsyncIterator[ProgressEvent]:
        """Stream of a run: run_start → status (agent announces) → run_end.

        Agents publish statuses via `context.announce(...)`; the app
        re-renders them in the chat ("Thinking…", "Searching docs…", "Found N…").
        At the end a run_end with a summary (outcome/runs/duration) is emitted.
        """
        queue = self.context.subscribe()
        done = asyncio.Event()

        async def _runner() -> None:
            try:
                await self.arun(max_iterations=max_iterations, budget=budget)
            finally:
                done.set()

        task = asyncio.create_task(_runner())
        try:
            yield ProgressEvent(kind="run_start", message="Processing started")
            while True:
                if done.is_set() and queue.empty():
                    break
                get_event = asyncio.ensure_future(queue.get())
                wait_done = asyncio.ensure_future(done.wait())
                finished, _ = await asyncio.wait(
                    {get_event, wait_done}, return_when=asyncio.FIRST_COMPLETED
                )
                if get_event in finished:
                    yield get_event.result()
                else:
                    get_event.cancel()
            # Re-raise any agent/runtime exception instead of silently dropping it:
            # an error inside a run must reach the caller, not hide in the task.
            await task
            stats = self.last_stats
            yield ProgressEvent(
                kind="run_end",
                message="Processing finished",
                data={
                    "outcome": stats.outcome.value if stats is not None else None,
                    "runs": stats.runs if stats is not None else 0,
                    "duration": stats.duration if stats is not None else 0.0,
                },
            )
        finally:
            task.cancel()
            self.context.unsubscribe(queue)

    def _apply_patch(self, patch: Patch, commit: Commit) -> list[Write]:
        writes: list[Write] = []
        for op in patch.operations:
            if isinstance(op, Create):
                if op.id is not None and self.context.get(op.id) is not None:
                    # create-or-refresh: after re-derivation update the same logical
                    # entity (new revision) rather than creating a duplicate (§42, §43)
                    upserted = self.context.update(op.id, op.data)
                    assert upserted is not None
                    op.artifact_id = op.id
                    writes.append(Write(op.id, upserted.version, "update"))
                else:
                    created = self.context.create(op.data, id=op.id)
                    op.artifact_id = created.id
                    created.created_by_commit = commit.id
                    writes.append(Write(op.artifact_id, created.version, "create"))
            elif isinstance(op, Update):
                updated = self.context.update(op.artifact_id, op.new_data)
                if updated is not None:
                    writes.append(Write(op.artifact_id, updated.version, "update"))
            elif isinstance(op, Delete):
                removed = self.context.get(op.artifact_id)
                version = removed.version if removed is not None else 0
                self.context.delete(op.artifact_id)
                writes.append(Write(op.artifact_id, version, "delete"))
            elif isinstance(op, Link):
                self.context.link(op.artifact_id, op.relation, op.target_id)
            elif isinstance(op, Unlink):
                self.context.unlink(op.artifact_id, op.relation, op.target_id)
            else:
                raise ValueError(f"Unknown operation: {op}")
        return writes
