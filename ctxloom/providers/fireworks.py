"""Fireworks AI — production inference (OpenAI-compatible)."""

from __future__ import annotations

from typing import Any

from .chat import OpenAICompatProvider, _network_knobs


def fireworks_llm(
    model: str = "accounts/fireworks/models/llama-v3p1-70b-instruct",
    base_url: str = "https://api.fireworks.ai/inference/v1",
    api_key: str | None = None,
    **kwargs: Any,
) -> OpenAICompatProvider:
    if api_key is None:
        import os

        api_key = os.getenv("FIREWORKS_API_KEY")
    merged = {**_network_knobs("FIREWORKS", kwargs), **kwargs}
    return OpenAICompatProvider(
        base_url=base_url, api_key=api_key, model=model, **merged
    )
