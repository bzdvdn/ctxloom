"""NVIDIA NIM — hosted open models (OpenAI-compatible)."""

from __future__ import annotations

from typing import Any

from .chat import OpenAICompatProvider, _network_knobs


def nvidia_nim_llm(
    model: str = "meta/llama-3.3-70b-instruct",
    base_url: str = "https://integrate.api.nvidia.com/v1",
    api_key: str | None = None,
    **kwargs: Any,
) -> OpenAICompatProvider:
    if api_key is None:
        import os

        api_key = os.getenv("NVIDIA_API_KEY")
    merged = {**_network_knobs("NVIDIA", kwargs), **kwargs}
    return OpenAICompatProvider(
        base_url=base_url, api_key=api_key, model=model, **merged
    )
