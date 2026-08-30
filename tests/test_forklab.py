"""forklab: the branch & merge demo runs deterministically (and, with a model,
calls the LLM throughout the flow — not just on the first request)."""

from ctxloom.providers import LLMProvider, LLMRequest, LLMResponse
from examples.forklab.main import _summary
from examples.forklab.models import Answer, Evidence
from examples.forklab.pipeline import run


class ScriptedLLM(LLMProvider):
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests: list[list[tuple[str, str]]] = []

    async def complete(self, request: LLMRequest) -> LLMResponse:
        self.requests.append([(m.role, m.content) for m in request.messages])
        return LLMResponse(text=self.responses.pop(0))

    async def stream(self, request):
        yield LLMResponse()  # pragma: no cover


def _word(raw: str) -> str:
    return '{"text": "' + raw + '"}'


def test_pipeline_merges_both_strategies():
    merged = run(question="Which design recovers the most thermal energy?")

    evidences = merged.list_artifacts(Evidence)
    by_branch: dict[str, int] = {}
    for evidence in evidences:
        by_branch[evidence.data.branch] = by_branch.get(evidence.data.branch, 0) + 1
    assert by_branch == {"depth": 1, "breadth": 3}

    answers = merged.list_artifacts(Answer)
    assert len(answers) == 1
    answer = answers[0]
    assert answer.data.sources[0] == "doc:overview"  # the strongest finding wins
    assert len(answer.data.sources) == 3

    # Answer is linked back to findings of BOTH branches (supported_by, §34)
    assert len(merged.relations()) == 4
    assert (
        "answer:merged" in merged.relations().__str__()
        or merged.get("answer:merged") is not None
    )


def test_pipeline_is_deterministic():
    first = run()
    second = run()
    assert [a.data.text for a in first.list_artifacts(Answer)] == [
        a.data.text for a in second.list_artifacts(Answer)
    ]
    assert first.version == second.version


def test_conflict_is_explicit_and_policy_resolves():

    merged = run(conflict=True)
    budget = merged.get("budget:1")
    assert budget is not None
    assert budget.data.tokens == 120  # policy kept the depth fork's value
    assert len(merged.list_artifacts(Answer)) == 1


def test_summary_reports_branch_split():
    merged = run()
    summary = _summary(merged)
    assert "depth" in summary
    assert "breadth" in summary
    assert "provenance links: 4" in summary


def test_llm_is_used_throughout_the_flow_not_just_first_call():
    llm = ScriptedLLM(
        [
            _word("LLM depth finding"),  # depth branch — 1 call
            _word("LLM breadth 1"),  # breadth branch — 3 calls
            _word("LLM breadth 2"),
            _word("LLM breadth 3"),
            _word("LLM synthesizes the merged answer."),  # evaluator — 1 call
        ]
    )
    merged = run(llm=llm)

    evidences = merged.list_artifacts(Evidence)
    by_branch: dict[str, list[str]] = {}
    for evidence in evidences:
        by_branch.setdefault(evidence.data.branch, []).append(evidence.data.text)
    # every finding was worded by the model, on both branches
    assert "LLM depth finding" in by_branch["depth"]
    assert len(by_branch["breadth"]) == 3
    assert all(t.startswith("LLM breadth") for t in by_branch["breadth"])

    answer = merged.list_artifacts(Answer)[0]
    assert answer.data.text == "LLM synthesizes the merged answer."

    # all five planned calls were consumed — the model ran through the whole flow
    assert llm.responses == []


def test_prompts_carry_the_domain_topic_and_question():

    llm = ScriptedLLM(
        [
            _word("LLM depth finding"),  # depth
            _word("LLM breadth 1"),  # breadth ×3
            _word("LLM breadth 2"),
            _word("LLM breadth 3"),
            _word("LLM answer"),  # synthesis
        ]
    )
    run(question="The question?", topic="marine battery safety", llm=llm)

    systems = [
        content for msgs in llm.requests for (role, content) in msgs if role == "system"
    ]
    assert len(systems) == 5
    for system in systems:
        assert "marine battery safety" in system  # the domain context is always present
        assert "The question?" in system  # the exact research question too
    assert any("lead analyst" in s for s in systems)  # synthesis has its own role
    assert len(systems) == 5  # wording (4) + synthesis (1) — not just the first
