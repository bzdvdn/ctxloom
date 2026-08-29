"""Console research assistant: asks questions against real web pages.

The pages are seeded from RESEARCH_URLS (comma-separated) or the default
Wikipedia topics. Run:

    .venv/bin/python examples/research/chat.py

Without an LLM key the answer is assembled deterministically from verified
claims (conf-detail fallback, §68).
"""

import asyncio
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ctxloom import Budget, Context, Runtime, RuntimeResources
from ctxloom.sources import WebSource

from examples.research.agents import research_agents
from examples.research.models import Answer, UserQuery

DEFAULT_URLS = [
    "https://en.wikipedia.org/wiki/Graphics_processing_unit",
    "https://en.wikipedia.org/wiki/Deep_learning",
]

ROOT = Path(__file__).resolve().parent


def build_resources() -> RuntimeResources:
    import os

    raw = os.getenv("RESEARCH_URLS")
    urls = [u.strip() for u in raw.split(",") if u.strip()] if raw else DEFAULT_URLS
    return RuntimeResources(
        llm=None,
        sources={"web": WebSource(urls=urls, source_id="web")},
    )


async def main() -> None:
    resources = build_resources()
    ctx = Context(resources=resources)
    runtime = Runtime(ctx, agents=research_agents(), budget=Budget(max_runs=120))

    print("Research assistant (Ctrl+C to exit). Seed pages:")
    for source in resources.sources.values():
        if isinstance(source, WebSource):
            for url, title in source.urls:
                print("  •", title or url)
    print()

    while True:
        text = input("You: ").strip()
        if text.lower() in {"exit", "quit"}:
            break
        if not text:
            continue
        query = ctx.create(UserQuery(text=text, session_id="research"))

        async def stream() -> None:
            async for event in runtime.astream():
                if event.kind == "status":
                    print(f"   {event.message}")

        await stream()

        answers = [a for a in ctx.list_artifacts(Answer) if a.data.query_id == query.id]
        if answers:
            latest = max(answers, key=lambda a: a.created_at)
            print("\nAnswer:")
            print(latest.data.text)
            if latest.data.sources:
                print("Sources:")
                for src in latest.data.sources:
                    print("  •", src)
        else:
            print("\n(no answer assembled)")
        print()


if __name__ == "__main__":
    asyncio.run(main())
