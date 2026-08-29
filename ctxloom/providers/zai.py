"""z.ai (Zhipu GLM) — chat (OpenAI-compatible)."""

from __future__ import annotations

from typing import Any

from .chat import OpenAICompatProvider, _network_knobs


def zai_llm(
    model: str = "glm-4.6",
    base_url: str = "https://api.z.ai/api/paas/v4",
    api_key: str | None = None,
    **kwargs: Any,
) -> OpenAICompatProvider:
    if api_key is None:
        import os

        api_key = os.getenv("ZAI_API_KEY")
    merged = {**_network_knobs("ZAI", kwargs), **kwargs}
    return OpenAICompatProvider(
        base_url=base_url, api_key=api_key, model=model, **merged
    )
