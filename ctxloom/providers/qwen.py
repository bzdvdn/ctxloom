"""Qwen (Alibaba DashScope) — chat (OpenAI-compatible)."""

from __future__ import annotations

from typing import Any

from .chat import OpenAICompatProvider, _network_knobs


def qwen_llm(
    model: str = "qwen-plus",
    base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1",
    api_key: str | None = None,
    **kwargs: Any,
) -> OpenAICompatProvider:
    if api_key is None:
        import os

        api_key = os.getenv("QWEN_API_KEY")
    merged = {**_network_knobs("QWEN", kwargs), **kwargs}
    return OpenAICompatProvider(
        base_url=base_url, api_key=api_key, model=model, **merged
    )
