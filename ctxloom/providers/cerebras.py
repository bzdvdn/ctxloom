"""Cerebras — ultra-fast inference (OpenAI-compatible)."""

from __future__ import annotations

from typing import Any

from .chat import OpenAICompatProvider, _network_knobs


def cerebras_llm(
    model: str = "llama-3.3-70b",
    base_url: str = "https://api.cerebras.ai/v1",
    api_key: str | None = None,
    **kwargs: Any,
) -> OpenAICompatProvider:
    if api_key is None:
        import os

        api_key = os.getenv("CEREBRAS_API_KEY")
    merged = {**_network_knobs("CEREBRAS", kwargs), **kwargs}
    return OpenAICompatProvider(
        base_url=base_url, api_key=api_key, model=model, **merged
    )
