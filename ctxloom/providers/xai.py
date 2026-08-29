"""xAI (Grok) — chat (OpenAI-compatible)."""

from __future__ import annotations

from typing import Any

from .chat import OpenAICompatProvider, _network_knobs


def xai_llm(
    model: str = "grok-4",
    base_url: str = "https://api.x.ai/v1",
    api_key: str | None = None,
    **kwargs: Any,
) -> OpenAICompatProvider:
    if api_key is None:
        import os

        api_key = os.getenv("XAI_API_KEY")
    merged = {**_network_knobs("XAI", kwargs), **kwargs}
    return OpenAICompatProvider(
        base_url=base_url, api_key=api_key, model=model, **merged
    )
