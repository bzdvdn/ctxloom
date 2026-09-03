import asyncio

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


class _SpyLLM(FakeLLM):
    def __init__(self) -> None:
        super().__init__()
        self.closed = False

    async def aclose(self) -> None:
        self.closed = True


class _SpyEmbedder(FakeEmbedder):
    def __init__(self) -> None:
        super().__init__()
        self.closed = False

    async def aclose(self) -> None:
        self.closed = True


def test_aclose_closes_llm_and_embedder_when_present():
    llm = _SpyLLM()
    embedder = _SpyEmbedder()
    resources = RuntimeResources(llm=llm, embedder=embedder)
    asyncio.run(resources.aclose())
    assert llm.closed is True
    assert embedder.closed is True


def test_aclose_is_a_noop_without_aclose_support():
    """FakeLLM/FakeEmbedder (and None) don't define aclose — duck-typed skip,
    not an AttributeError."""
    resources = RuntimeResources(llm=FakeLLM(), embedder=FakeEmbedder())
    asyncio.run(resources.aclose())  # must not raise

    empty = RuntimeResources()
    asyncio.run(empty.aclose())  # must not raise
