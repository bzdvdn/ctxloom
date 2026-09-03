"""Perplexity — Sonar answer API (OpenAI-compatible, built-in web search)."""

from __future__ import annotations

from .chat import _openai_compat_llm

perplexity_llm = _openai_compat_llm(
    env_prefix="PERPLEXITY",
    default_model="sonar-pro",
    default_base_url="https://api.perplexity.ai",
)
