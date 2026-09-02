"""OpenRouter — model router: chat (fast mode by default) and images."""

from __future__ import annotations

from typing import Any

from .chat import OpenAICompatProvider, _network_knobs
from .image import OpenAICompatImageProvider


def openrouter_llm(
    model: str = "deepseek/deepseek-v4-flash",
    base_url: str = "https://openrouter.ai/api/v1",
    api_key: str | None = None,
    **kwargs: Any,
) -> OpenAICompatProvider | None:
    import os

    if api_key is None:
        api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        return None  # without a key OpenRouter does not work — the app falls back
    model = os.getenv("OPENROUTER_MODEL") or model
    extra_body: dict[str, Any] = dict(kwargs.pop("extra_body", None) or {})
    # hybrid models: disable reasoning by default (fast mode)
    extra_body.setdefault("reasoning", {"enabled": False})
    merged = {**_network_knobs("OPENROUTER", kwargs), **kwargs}
    return OpenAICompatProvider(
        base_url=base_url,
        api_key=api_key,
        model=model,
        extra_body=extra_body,
        **merged,
    )


def openrouter_image(
    model: str = "google/gemini-3-pro-create-image-plus",
    base_url: str = "https://openrouter.ai/api/v1",
    api_key: str | None = None,
    **kwargs: Any,
) -> OpenAICompatImageProvider:
    if api_key is None:
        import os

        api_key = os.getenv("OPENROUTER_API_KEY")
    merged = {**_network_knobs("OPENROUTER", kwargs), **kwargs}
    return OpenAICompatImageProvider(
        base_url=base_url, api_key=api_key, model=model, **merged
    )
