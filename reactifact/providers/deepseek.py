"""DeepSeek — cloud chat (deepseek-chat / deepseek-reasoner)."""

from __future__ import annotations

from .chat import _openai_compat_llm

deepseek_llm = _openai_compat_llm(
    env_prefix="DEEPSEEK",
    default_model="deepseek-chat",
    default_base_url="https://api.deepseek.com",
)
