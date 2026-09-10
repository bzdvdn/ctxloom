"""Mistral AI — cloud chat and embeddings (OpenAI-compatible)."""

from __future__ import annotations

from .chat import _openai_compat_embedder, _openai_compat_llm

mistral_llm = _openai_compat_llm(
    env_prefix="MISTRAL",
    default_model="mistral-large-latest",
    default_base_url="https://api.mistral.ai/v1",
)

mistral_embedder = _openai_compat_embedder(
    env_prefix="MISTRAL",
    default_model="mistral-embed",
    default_base_url="https://api.mistral.ai/v1",
)
