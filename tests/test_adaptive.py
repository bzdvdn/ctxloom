"""Adaptive scheduling (§26, §24): filter → rank → LLM tie-break, HITL pin."""

import asyncio

from ctxloom import Context, PendingQuestion, RuntimeResources
from ctxloom.providers import LLMProvider, LLMRequest, LLMResponse
from ctxloom.scheduler import uncertainty_policy
from examples.adaptive.main import RULES, ArtistA, ArtistB, Task, _metric


class ScriptedLLM(LLMProvider):
    def __init__(self, responses):
        self.responses = list(responses)

    async def complete(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(text=self.responses.pop(0))

    async def stream(self, request):
        yield LLMResponse()  # pragma: no cover


def _event_for(ctx: Context, artifact_id: str):
    events = ctx.drain_events()
    for e in events:
        if e.artifact_id == artifact_id:
            return e
    return None


def _ctx_with_task(tag: str = "") -> tuple[Context, object]:
    ctx = Context(resources=RuntimeResources())
    task = ctx.create(Task(text="Summarize the money plan.", tag=tag))
    return ctx, task


def test_scheduler_ranks_b_first_for_money():
    ctx, task = _ctx_with_task()
    event = _event_for(ctx, task.id)
    policy = uncertainty_policy(metric=_metric)
    a, b = (ArtistA(), event, []), (ArtistB(), event, [])
    out = asyncio.run(policy(ctx, [a, b]))
    assert out == [b, a]  # metric prefers 'b' when the task mentions money


def test_scheduler_filter_prunes_before_ranking():
    ctx, task = _ctx_with_task(tag="x")
    event = _event_for(ctx, task.id)
    policy = uncertainty_policy(rules=RULES, metric=_metric)
    a, b = (ArtistA(), event, []), (ArtistB(), event, [])
    out = asyncio.run(policy(ctx, [a, b]))
    assert out == [a]  # 'b' never reaches ranking


def test_scheduler_no_starvation_fallback():
    ctx, task = _ctx_with_task()
    event = _event_for(ctx, task.id)

    def kill_all(context, agent, evt) -> bool:
        return False

    policy = uncertainty_policy(rules=[kill_all], metric=_metric)
    a, b = (ArtistA(), event, []), (ArtistB(), event, [])
    out = asyncio.run(policy(ctx, [a, b]))
    assert len(out) == 2  # the original set survives a rule that prunes everything


def test_scheduler_llm_tiebreak_orders_when_available():
    ctx = Context(resources=RuntimeResources(llm=ScriptedLLM(['{"first":1}'])))
    task = ctx.create(Task(text="Summarize the room plan.", tag=""))
    event = _event_for(ctx, task.id)
    policy = uncertainty_policy(metric=_metric, llm_tie_break=1.0)
    a, b = (ArtistA(), event, []), (ArtistB(), event, [])
    out = asyncio.run(policy(ctx, [a, b]))
    assert out == [b, a]  # a tie (no "money") → the model moved 'b' first


def test_scheduler_offline_skips_llm_tiebreak():
    ctx, task = _ctx_with_task()
    event = _event_for(ctx, task.id)
    policy = uncertainty_policy(metric=_metric, llm_tie_break=1.0)  # llm=None
    a, b = (ArtistA(), event, []), (ArtistB(), event, [])
    out = asyncio.run(policy(ctx, [a, b]))
    assert out == [b, a]  # deterministic metric still applies


def test_scheduler_pins_hitl_resume_first():

    ctx = Context(resources=RuntimeResources())
    task = ctx.create(Task(text="Summarize the room plan.", tag=""))
    te = _event_for(ctx, task.id)
    question = ctx.create(PendingQuestion(question="Approve?", kind="approval"))
    ctx.update(
        question.id,
        PendingQuestion(
            question="Approve?", kind="approval", answered=True, resolution="yes"
        ),
    )
    re = _event_for(ctx, question.id)

    policy = uncertainty_policy(metric=_metric)
    a_event, b_event = (ArtistA(), te, []), (ArtistB(), te, [])
    out = asyncio.run(policy(ctx, [(ArtistA(), re, []), a_event, b_event]))
    assert out[0][1].artifact_id == question.id  # resume runs first, then ranked


def test_adaptive_demo_offline_uses_metric_and_hitl():
    from examples.adaptive.main import Final, run

    ctx = run(tag="", text="Summarize the room plan and the money estimate.", llm=None)
    final = ctx.list_artifacts(Final)[0]
    assert final.data.by == "b"  # money → metric prefers 'b'


def test_adaptive_demo_rule_prunes_candidate():
    from examples.adaptive.main import Final, Summary, run

    ctx = run(tag="x", text="Summarize the room plan and the money estimate.", llm=None)
    assert not [s for s in ctx.list_artifacts(Summary) if s.data.by == "b"]
    final = ctx.list_artifacts(Final)[0]
    assert final.data.by == "a"


def test_scheduler_uses_custom_llm_system():
    from ctxloom.scheduler import uncertainty_policy

    class Capture(LLMProvider):
        def __init__(self):
            self.system = None

        async def complete(self, request):
            self.system = request.messages[0].content
            return LLMResponse(text='{"first":1}')

        async def stream(self, request):
            yield LLMResponse()  # pragma: no cover

    llm = Capture()
    ctx = Context(resources=RuntimeResources(llm=llm))
    task = ctx.create(Task(text="Summarize the room plan.", tag=""))
    event = _event_for(ctx, task.id)

    policy = uncertainty_policy(
        metric=_metric,
        llm_tie_break=1.0,
        llm_system="You pick the first artist. Reply with the index.",
    )
    a, b = (ArtistA(), event, []), (ArtistB(), event, [])
    out = asyncio.run(policy(ctx, [a, b]))
    assert out == [b, a]
    assert llm.system == "You pick the first artist. Reply with the index."


def test_scheduler_rank_limit_keeps_only_top():
    ctx, task = _ctx_with_task()  # "money" → 'b' is the top candidate
    event = _event_for(ctx, task.id)
    policy = uncertainty_policy(metric=_metric, rank_limit=1)
    a, b = (ArtistA(), event, []), (ArtistB(), event, [])
    out = asyncio.run(policy(ctx, [a, b]))
    assert out == [b]  # only the best-ranked candidate survives


def test_scheduler_rank_limit_never_starves():
    ctx, task = _ctx_with_task()
    event = _event_for(ctx, task.id)
    policy = uncertainty_policy(metric=_metric, rank_limit=1)
    a, b = (ArtistA(), event, []), (ArtistB(), event, [])
    out = asyncio.run(policy(ctx, [a, b]))
    assert len(out) >= 1  # a non-empty ranked list is never emptied
