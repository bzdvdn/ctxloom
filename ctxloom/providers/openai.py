"""OpenAI — cloud chat and embeddings."""

from __future__ import annotations

from typing import Any

from .chat import OpenAICompatEmbedder, OpenAICompatProvider, _network_knobs


def openai_llm(
    model: str = "gpt-4o-mini",
    base_url: str = "https://api.openai.com/v1",
    api_key: str | None = None,
    **kwargs: Any,
) -> OpenAICompatProvider:
    if api_key is None:
        import os

        api_key = os.getenv("OPENAI_API_KEY")
    merged = {**_network_knobs("OPENAI", kwargs), **kwargs}
    return OpenAICompatProvider(
        base_url=base_url, api_key=api_key, model=model, **merged
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
