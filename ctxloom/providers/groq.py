"""Groq — fast inference (OpenAI-compatible)."""

from __future__ import annotations

from typing import Any

from .chat import OpenAICompatProvider, _network_knobs


def groq_llm(
    model: str = "llama-3.3-70b-versatile",
    base_url: str = "https://api.groq.com/openai/v1",
    api_key: str | None = None,
    **kwargs: Any,
) -> OpenAICompatProvider:
    if api_key is None:
        import os

        api_key = os.getenv("GROQ_API_KEY")
    merged = {**_network_knobs("GROQ", kwargs), **kwargs}
    return OpenAICompatProvider(
        base_url=base_url, api_key=api_key, model=model, **merged
    )
