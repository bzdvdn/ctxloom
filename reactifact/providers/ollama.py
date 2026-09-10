"""Ollama (local, OpenAI-compatible /v1)."""

from __future__ import annotations

from typing import Any

from .chat import OpenAICompatProvider


def ollama_llm(
    model: str = "qwen2.5:7b",
    base_url: str = "http://localhost:11434/v1",
    timeout: float = 120.0,
    **kwargs: Any,
) -> OpenAICompatProvider:
    return OpenAICompatProvider(
        base_url=base_url, model=model, timeout=timeout, **kwargs
    )
