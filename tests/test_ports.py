"""Ports of canonical framework examples — deterministic (offline) behavior."""

from ctxloom.providers import LLMProvider, LLMRequest, LLMResponse


class ScriptedLLM(LLMProvider):
    def __init__(self, responses):
        self.responses = list(responses)

    async def complete(self, request: LLMRequest) -> LLMResponse:
        text = self.responses.pop(0) if self.responses else '{"text":"retry"}'
        return LLMResponse(text=text)

    async def stream(self, request):
        yield LLMResponse()  # pragma: no cover


def test_reflection_reaches_final_offline():
    from examples.reflection.main import Draft, Final, Review
    from examples.reflection.main import run as run_reflection

    ctx = run_reflection(topic="Hydro")
    finals = ctx.list_artifacts(Final)
    assert len(finals) == 1
    assert finals[0].data.rounds <= 2
    assert ctx.list_artifacts(Draft)
    assert ctx.list_artifacts(Review)


def test_reflection_accepts_early_with_model():
    from examples.reflection.main import Draft, Final
    from examples.reflection.main import run as run_reflection

    llm = ScriptedLLM(['{"text":"draft one"}', '{"score":0.95,"feedback":"solid"}'])
    ctx = run_reflection(topic="Hydro", llm=llm)
    final = ctx.list_artifacts(Final)[0]
    draft = ctx.list_artifacts(Draft)[0]
    assert final.data.text == "draft one"
    assert draft.data.status == "accepted"
    assert final.data.rounds == 0


def test_map_reduce_splits_summarizes_and_combines():
    from examples.map_reduce.main import (
        Chunk,
        ChunkSummary,
        FinalSummary,
    )
    from examples.map_reduce.main import (
        run as run_map,
    )

    ctx = run_map(source="word " * 90)
    assert len(ctx.list_artifacts(Chunk)) == 3
    assert len(ctx.list_artifacts(ChunkSummary)) == 3
    finals = ctx.list_artifacts(FinalSummary)
    assert len(finals) == 1
    assert len(finals[0].data.sources) == 3
    assert len(ctx.related(finals[0].id, relation="supported_by")) == 3


def test_supervisor_approval_pipeline():
    from examples.supervisor.main import (
        FinalReply,
        PendingQuestion,
        SpecialistReport,
    )
    from examples.supervisor.main import (
        run as run_sup,
    )

    ctx = run_sup(text="оптимизируйте бюджет")
    assert ctx.list_artifacts(SpecialistReport)
    replies = ctx.list_artifacts(FinalReply)
    assert len(replies) == 1
    # approval is recorded exactly once, and answered
    approvals = [
        q for q in ctx.list_artifacts(PendingQuestion) if q.data.kind == "approval"
    ]
    assert len(approvals) == 1
    assert approvals[0].data.answered is True


def test_summarize_keeps_window_and_memory_artifact():
    from examples.summarize.main import Msg, Summary
    from examples.summarize.main import run as run_sum

    ctx = run_sum(
        seed=[
            "a: один",
            "b: два",
            "c: три",
            "d: четыре",
        ]
    )
    summaries = ctx.list_artifacts(Summary)
    assert summaries and any(s.data.round == 2 for s in summaries)
    assert len(ctx.list_artifacts(Msg)) == 4  # window kept


def test_time_travel_forks_merges_and_picks():
    from examples.time_travel.main import Candidate, Decision
    from examples.time_travel.main import run as run_tt

    ctx = run_tt(text="how to present")
    candidates = ctx.list_artifacts(Candidate)
    assert {c.data.name for c in candidates} == {"a", "b"}
    decisions = ctx.list_artifacts(Decision)
    assert len(decisions) == 1
    assert len(ctx.related(decisions[0].id, relation="supported_by")) == 2
