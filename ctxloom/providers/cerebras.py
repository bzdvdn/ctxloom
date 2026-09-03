"""Cerebras — ultra-fast inference (OpenAI-compatible)."""

from __future__ import annotations

from .chat import _openai_compat_llm

cerebras_llm = _openai_compat_llm(
    env_prefix="CEREBRAS",
    default_model="llama-3.3-70b",
    default_base_url="https://api.cerebras.ai/v1",
)
