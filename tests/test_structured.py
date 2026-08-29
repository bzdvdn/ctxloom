import asyncio

from ctxloom import (
    Consume,
    Context,
    Runtime,
    RuntimeResources,
    StructuredGenerate,
    parse_structured,
    structured_llm,
)
from ctxloom.providers import LLMProvider, LLMRequest, LLMResponse
from pydantic import BaseModel


class Summary(BaseModel):
    text: str
    topics: list[str] = []


class ScriptedLLM(LLMProvider):
    def __init__(self, responses):
        self.responses = list(responses)

    async def complete(self, request: LLMRequest) -> LLMResponse:
        text = self.responses.pop(0) if self.responses else ""
        return LLMResponse(text=text)

    async def stream(self, request):
        yield LLMResponse(text="")  # pragma: no cover


def test_tolerant_parse_with_fences_and_noise():
    raw = 'Вот ответ:\n```json\n{"text": "итог", "topics": ["a", "b"]}\n```\nспасибо'
    summary = parse_structured(raw, Summary)
    assert summary is not None
    assert summary.text == "итог"
    assert summary.topics == ["a", "b"]


def test_parse_ignores_garbage():
    assert parse_structured("не json вообще", Summary) is None


def test_structured_llm_retries_on_invalid_json():
    llm = ScriptedLLM(
        [
            "К сожалению, не смог сгенерировать.",
            '{"text": "ок", "topics": []}',
        ]
    )
    ctx = Context(resources=RuntimeResources(llm=llm))

    result = asyncio.run(structured_llm(ctx, schema=Summary, user="сделай итог"))
    assert result is not None
    assert result.text == "ок"
    assert len(llm.responses) == 0  # both calls used


def test_structured_llm_returns_none_on_all_failures():
    llm = ScriptedLLM(["мусор", "ещё мусор"])
    ctx = Context(resources=RuntimeResources(llm=llm))

    result = asyncio.run(structured_llm(ctx, schema=Summary, user="итог", attempts=2))
    assert result is None


class Report(BaseModel):
    title: str
    body: str


class Article(BaseModel):
    content: str


class ReportGenerator(StructuredGenerate):
    name = "report_generator"
    schema = Report
    consumes = [Consume(Article)]

    def build_prompt(self, inputs):
        return f"Сделай отчёт о статье: {inputs[0].data.content}"

    def fallback(self, inputs):
        return Report(title="fallback", body=inputs[0].data.content[:50])


def test_structured_generate_agent_uses_llm():
    llm = ScriptedLLM(['{"title": "Т", "body": "Б"}'])
    ctx = Context(resources=RuntimeResources(llm=llm))
    runtime = Runtime(ctx, agents=[ReportGenerator()])
    ctx.create(Article(content="статья про отчёты"))
    asyncio.run(runtime.arun())

    reports = ctx.list_artifacts(Report)
    assert len(reports) == 1
    assert reports[0].data.title == "Т"
    commit = ctx.history()[-1]
    assert commit.author == "report_generator"


def test_structured_generate_fallback_on_llm_failure():
    llm = ScriptedLLM(["не валидный json", "тоже не валидный"])
    ctx = Context(resources=RuntimeResources(llm=llm))
    runtime = Runtime(ctx, agents=[ReportGenerator()])
    ctx.create(Article(content="очень длинная статья"))
    asyncio.run(runtime.arun())

    reports = ctx.list_artifacts(Report)
    assert len(reports) == 1
    assert reports[0].data.title == "fallback"


def test_structured_llm_without_llm_returns_none():
    ctx = Context()
    result = asyncio.run(structured_llm(ctx, schema=Summary, user="x"))
    assert result is None


class FlakyLLM(LLMProvider):
    def __init__(self):
        self.calls = 0

    async def complete(self, request: LLMRequest) -> LLMResponse:
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("network blip")
        return LLMResponse(text='{"text": "ok", "topics": []}')

    async def stream(self, request):
        yield LLMResponse(text="")


def test_structured_llm_retries_on_network_error():
    llm = FlakyLLM()
    ctx = Context(resources=RuntimeResources(llm=llm))
    result = asyncio.run(structured_llm(ctx, schema=Summary, user="x"))
    assert result is not None
    assert result.text == "ok"
    assert llm.calls == 2
