"""xAI (Grok) — chat (OpenAI-compatible)."""

from __future__ import annotations

from .chat import _openai_compat_llm

xai_llm = _openai_compat_llm(
    env_prefix="XAI",
    default_model="grok-4",
    default_base_url="https://api.x.ai/v1",
)
