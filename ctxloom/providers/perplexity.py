"""Perplexity — Sonar answer API (OpenAI-compatible, built-in web search)."""

from __future__ import annotations

from typing import Any

from .chat import OpenAICompatProvider, _network_knobs


def perplexity_llm(
    model: str = "sonar-pro",
    base_url: str = "https://api.perplexity.ai",
    api_key: str | None = None,
    **kwargs: Any,
) -> OpenAICompatProvider:
    if api_key is None:
        import os

        api_key = os.getenv("PERPLEXITY_API_KEY")
    merged = {**_network_knobs("PERPLEXITY", kwargs), **kwargs}
    return OpenAICompatProvider(
        base_url=base_url, api_key=api_key, model=model, **merged
    )
