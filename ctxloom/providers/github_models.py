"""GitHub Models — OpenAI-compatible model playground with a free tier."""

from __future__ import annotations

from .chat import _openai_compat_llm

github_models_llm = _openai_compat_llm(
    env_prefix="GITHUB",
    default_model="gpt-4o-mini",
    default_base_url="https://models.github.ai/v1",
    env_api_key_vars=("GITHUB_TOKEN", "GITHUB_API_KEY"),
    name="github_models_llm",
)
