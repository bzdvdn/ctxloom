"""Fireworks AI — production inference (OpenAI-compatible), plus embeddings."""

from __future__ import annotations

from .chat import _openai_compat_embedder, _openai_compat_llm

fireworks_llm = _openai_compat_llm(
    env_prefix="FIREWORKS",
    default_model="accounts/fireworks/models/llama-v3p1-70b-instruct",
    default_base_url="https://api.fireworks.ai/inference/v1",
)

fireworks_embedder = _openai_compat_embedder(
    env_prefix="FIREWORKS",
    default_model="nomic-ai/nomic-embed-text-v1.5",
    default_base_url="https://api.fireworks.ai/inference/v1",
)
