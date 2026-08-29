"""GitHub Models — OpenAI-compatible model playground with a free tier."""

from __future__ import annotations

from typing import Any

from .chat import OpenAICompatProvider, _network_knobs


def github_models_llm(
    model: str = "gpt-4o-mini",
    base_url: str = "https://models.github.ai/v1",
    api_key: str | None = None,
    **kwargs: Any,
) -> OpenAICompatProvider:
    if api_key is None:
        import os

        api_key = os.getenv("GITHUB_TOKEN") or os.getenv("GITHUB_API_KEY")
    merged = {**_network_knobs("GITHUB", kwargs), **kwargs}
    return OpenAICompatProvider(
        base_url=base_url, api_key=api_key, model=model, **merged
    )
