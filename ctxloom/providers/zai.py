"""z.ai (Zhipu GLM) — chat (OpenAI-compatible)."""

from __future__ import annotations

from .chat import _openai_compat_llm

zai_llm = _openai_compat_llm(
    env_prefix="ZAI",
    default_model="glm-4.6",
    default_base_url="https://api.z.ai/api/paas/v4",
)
