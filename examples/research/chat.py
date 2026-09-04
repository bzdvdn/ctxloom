"""Console research assistant: asks questions against real web pages.

The pages are seeded from RESEARCH_URLS (comma-separated) or the default
Wikipedia topics. Run:

    .venv/bin/python examples/research/chat.py

Without an LLM key (OPENROUTER_API_KEY or OPENAI_BASE_URL in .env) the answer
is assembled deterministically from verified claims (conf-detail fallback,
§68) — a raw excerpt of the page, not a summary.
"""

import asyncio
import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ctxloom import Budget, Context, Runtime, RuntimeResources
from ctxloom.providers import openai_llm, openrouter_llm
from ctxloom.sources import WebSource
from dotenv import load_dotenv

from examples.research.agents import research_agents
from examples.research.models import Answer, UserQuery

DEFAULT_URLS = [
    "https://en.wikipedia.org/wiki/Graphics_processing_unit",
    "https://en.wikipedia.org/wiki/Deep_learning",
]

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

#: Sentinel: resolve the LLM from the environment (the demo default).
_UNSET = object()


def build_llm() -> Any:
    """Explicit provider for this demo: OpenRouter (default) or a local
    OpenAI-compatible endpoint; `None` when no key is configured → the demo
    runs on the deterministic claim-based fallback (§68)."""
    import os

    if os.getenv("OPENROUTER_API_KEY"):
        return openrouter_llm(max_tokens=2048)
    if os.getenv("OPENAI_BASE_URL"):
        return openai_llm(
            base_url=os.getenv("OPENAI_BASE_URL", ""),
            api_key=os.getenv("OPENAI_API_KEY", ""),
            model=os.getenv("OPENAI_MODEL", ""),
            max_tokens=2048,
        )
    return None


def build_resources(llm: Any = _UNSET) -> RuntimeResources:
    """The demo's sources (+ optional LLM). `llm`: from env by default;
    pass an explicit provider or `None` for hermetic tests/fallbacks."""
    import os

    if llm is _UNSET:
        llm = build_llm()
    raw = os.getenv("RESEARCH_URLS")
    urls = [u.strip() for u in raw.split(",") if u.strip()] if raw else DEFAULT_URLS
    return RuntimeResources(
        llm=llm,
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
