"""Together AI — hosted open models (OpenAI-compatible)."""

from __future__ import annotations

from typing import Any

from .chat import OpenAICompatProvider, _network_knobs


def together_llm(
    model: str = "meta-llama/Llama-3.3-70B-Instruct-Turbo",
    base_url: str = "https://api.together.xyz/v1",
    api_key: str | None = None,
    **kwargs: Any,
) -> OpenAICompatProvider:
    if api_key is None:
        import os

        api_key = os.getenv("TOGETHER_API_KEY")
    merged = {**_network_knobs("TOGETHER", kwargs), **kwargs}
    return OpenAICompatProvider(
        base_url=base_url, api_key=api_key, model=model, **merged
    )
