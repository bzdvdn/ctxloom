"""DeepSeek — cloud chat (deepseek-chat / deepseek-reasoner)."""

from __future__ import annotations

from typing import Any

from .chat import OpenAICompatProvider


def deepseek_llm(
    model: str = "deepseek-chat",
    base_url: str = "https://api.deepseek.com",
    api_key: str | None = None,
    **kwargs: Any,
) -> OpenAICompatProvider:
    if api_key is None:
        import os

        api_key = os.getenv("DEEPSEEK_API_KEY")
    return OpenAICompatProvider(
        base_url=base_url, api_key=api_key, model=model, **kwargs
    )
