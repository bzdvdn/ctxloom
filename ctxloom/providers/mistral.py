"""Mistral AI — cloud chat and embeddings (OpenAI-compatible)."""

from __future__ import annotations

from typing import Any

from .chat import OpenAICompatEmbedder, OpenAICompatProvider, _network_knobs


def mistral_llm(
    model: str = "mistral-large-latest",
    base_url: str = "https://api.mistral.ai/v1",
    api_key: str | None = None,
    **kwargs: Any,
) -> OpenAICompatProvider:
    if api_key is None:
        import os

        api_key = os.getenv("MISTRAL_API_KEY")
    merged = {**_network_knobs("MISTRAL", kwargs), **kwargs}
    return OpenAICompatProvider(
        base_url=base_url, api_key=api_key, model=model, **merged
    )


def mistral_embedder(
    model: str = "mistral-embed",
    base_url: str = "https://api.mistral.ai/v1",
    api_key: str | None = None,
    **kwargs: Any,
) -> OpenAICompatEmbedder:
    if api_key is None:
        import os

        api_key = os.getenv("MISTRAL_API_KEY")
    merged = {**_network_knobs("MISTRAL", kwargs), **kwargs}
    return OpenAICompatEmbedder(
        base_url=base_url, api_key=api_key, model=model, **merged
    )
