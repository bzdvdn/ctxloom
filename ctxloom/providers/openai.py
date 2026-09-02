"""OpenAI — cloud chat and embeddings."""

from __future__ import annotations

from typing import Any

from .chat import OpenAICompatEmbedder, OpenAICompatProvider, _network_knobs


def openai_llm(
    model: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    **kwargs: Any,
) -> OpenAICompatProvider | None:
    if api_key is None:
        import os

        api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None  # without a key the app runs on its deterministic fallbacks
    merged = {**_network_knobs("OPENAI", kwargs), **kwargs}
    return OpenAICompatProvider(
        base_url=base_url or "https://api.openai.com/v1",
        api_key=api_key,
        model=model or "gpt-4o-mini",
        **merged,
    )


def openai_embedder(
    model: str = "text-embedding-3-small",
    base_url: str = "https://api.openai.com/v1",
    api_key: str | None = None,
    **kwargs: Any,
) -> OpenAICompatEmbedder:
    if api_key is None:
        import os

        api_key = os.getenv("OPENAI_API_KEY")
    merged = {**_network_knobs("OPENAI", kwargs), **kwargs}
    return OpenAICompatEmbedder(
        base_url=base_url, api_key=api_key, model=model, **merged
    )
