"""Research demo: a web research question answered from live-fetched pages.

Hermetic: WebSource uses an injected MockTransport, so no real network.
"""

import asyncio

import httpx
from ctxloom import Budget, Context, Runtime, RuntimeResources
from ctxloom.sources import WebSource
from examples.research.agents import research_agents
from examples.research.models import Answer, Claim, Evidence, UserQuery

PAGES = {
    "https://example.org/gpu": (
        "<html><title>GPU inference</title><body><h1>GPU inference</h1>"
        "<p>GPUs speed up inference with many parallel cores.</p></body></html>"
    ),
    "https://example.org/ml": (
        "<html><title>Machine learning</title><body><h1>ML</h1>"
        "<p>mostly it is math and data.</p></body></html>"
    ),
}


def build():
    transport = httpx.MockTransport(
        lambda req: httpx.Response(200, text=PAGES[str(req.url)])
    )
    resources = RuntimeResources(
        llm=None,
        sources={"web": WebSource(urls=list(PAGES), transport=transport)},
    )
    ctx = Context(resources=resources)
    runtime = Runtime(ctx, agents=research_agents(), budget=Budget(max_runs=120))
    return ctx, runtime


def test_research_answers_from_web():
    ctx, runtime = build()
    query = ctx.create(UserQuery(text="how does a gpu speed up inference?"))
    asyncio.run(runtime.arun())

    answers = [a for a in ctx.list_artifacts(Answer) if a.data.query_id == query.id]
    assert len(answers) == 1
    answer = answers[0].data
    assert answer.text.strip()
    # the winning source is the GPU page, cited by URL (provenance, §34)
    assert any("https://example.org/gpu" in s for s in answer.sources)


def test_research_provenance_chain():
    ctx, runtime = build()
    query = ctx.create(UserQuery(text="what is machine learning?"))
    asyncio.run(runtime.arun())

    claims = [c for c in ctx.list_artifacts(Claim) if c.data.query_id == query.id]
    assert claims
    for claim in claims:
        evidences = ctx.related(claim.id, relation="derived_from")
        assert evidences and type(evidences[0].data) is Evidence
        docs = ctx.related(evidences[0].id, relation="extracted_from")
        assert len(docs) == 1
        assert docs[0].data.path == "https://example.org/ml"


def test_insufficient_when_nothing_matches():
    transport = httpx.MockTransport(
        lambda req: httpx.Response(
            200, text="<html><body>unrelated static content</body></html>"
        )
    )
    resources = RuntimeResources(
        llm=None,
        sources={"web": WebSource(urls=["https://example.org/x"], transport=transport)},
    )
    ctx = Context(resources=resources)
    runtime = Runtime(ctx, agents=research_agents(), budget=Budget(max_runs=120))
    ctx.create(UserQuery(text="sky density balloon thresholds"))
    asyncio.run(runtime.arun())
    assert ctx.list_artifacts(Answer) == []
