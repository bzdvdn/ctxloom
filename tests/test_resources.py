from ctxloom.context import Context
from ctxloom.providers import FakeEmbedder, FakeLLM
from ctxloom.resources import RuntimeResources


def test_runtime_resources_init():
    resources = RuntimeResources()
    assert resources.llm is None
    assert resources.embedder is None


def test_runtime_resources_custom():
    llm = FakeLLM()
    embedder = FakeEmbedder()
    resources = RuntimeResources(llm=llm, embedder=embedder)
    assert resources.llm is llm
    assert resources.embedder is embedder


def test_runtime_resources_additional():
    resources = RuntimeResources()
    resources.set("custom", 42)
    assert resources.get("custom") == 42


def test_context_resources():
    llm = FakeLLM()
    resources = RuntimeResources(llm=llm)
    ws = Context(resources=resources)
    assert ws.resources.llm is llm
