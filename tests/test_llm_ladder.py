"""llm-ladder: the three levels behave deterministically, with and without an LLM."""

from ctxloom.providers import LLMProvider, LLMRequest, LLMResponse
from examples.llm_ladder.level1 import Answer as L1Answer
from examples.llm_ladder.level1 import run as run_l1
from examples.llm_ladder.level2 import (
    Answer as L2Answer,
)
from examples.llm_ladder.level2 import (
    Evidence,
)
from examples.llm_ladder.level2 import (
    run as run_l2,
)
from examples.llm_ladder.level3 import (
    Answer as L3Answer,
)
from examples.llm_ladder.level3 import (
    Claim,
    Turn,
)
from examples.llm_ladder.level3 import (
    run as run_l3,
)


class ScriptedLLM(LLMProvider):
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = 0

    async def complete(self, request: LLMRequest) -> LLMResponse:
        self.requests += 1
        text = self.responses.pop(0) if self.responses else '{"text": "retry fallback"}'
        return LLMResponse(text=text)

    async def stream(self, request):
        yield LLMResponse()  # pragma: no cover


def _text(payload: str) -> str:
    return '{"text": "' + payload + '"}'


def test_level1_offline_falls_back_honestly():
    ctx = run_l1(question="three states of water?")
    answers = ctx.list_artifacts(L1Answer)
    assert len(answers) == 1
    assert "(no answer)" in answers[0].data.text


def test_level1_with_model_uses_the_answer():
    llm = ScriptedLLM([_text("solid, liquid, gas")])
    ctx = run_l1(llm=llm, question="three states of water?")
    answers = ctx.list_artifacts(L1Answer)
    assert answers[0].data.text == "solid, liquid, gas"
    assert llm.requests == 1


def test_level2_linked_patch_and_provenance():
    llm = ScriptedLLM([_text("storage ~75% efficient")])
    ctx = run_l2(llm=llm)
    answers = ctx.list_artifacts(L2Answer)
    assert len(answers) == 1
    answer = answers[0]
    assert answer.data.text  # an LLM-produced answer (not the offline fallback)
    assert "(offline" not in answer.data.text
    assert answer.data.sources == ["docs/hydro.md"]

    evidences = ctx.list_artifacts(Evidence)
    assert len(evidences) == 1
    linked = ctx.related(answer.id, relation="supported_by")
    assert linked and linked[0] is evidences[0]
    docs = ctx.related(evidences[0].id, relation="extracted_from")
    assert len(docs) == 1
    assert llm.requests >= 2  # the model ran more than once across the flow


def test_level3_lifecycle_reaches_answered_and_links():
    llm = ScriptedLLM(
        [
            _text("the electron has wave properties"),
            '{"text": "wave-particle duality", "confidence": 0.9}',
        ]
    )
    ctx = run_l3(llm=llm)

    turns = ctx.list_artifacts(Turn)
    assert len(turns) == 1
    assert turns[0].data.status == "answered"

    claims = ctx.list_artifacts(Claim)
    assert len(claims) == 1
    assert claims[0].data.text == "the electron has wave properties"

    answers = ctx.list_artifacts(L3Answer)
    assert len(answers) == 1
    linked = ctx.related(answers[0].id, relation="supported_by")
    assert len(linked) == 1
    assert linked[0].id == claims[0].id
    assert llm.requests == 2


def test_level3_offline_still_completes_lifecycle():
    ctx = run_l3(question="is it warm outside?")
    turns = ctx.list_artifacts(Turn)
    assert turns and turns[0].data.status == "answered"
    assert len(ctx.list_artifacts(L3Answer)) == 1
