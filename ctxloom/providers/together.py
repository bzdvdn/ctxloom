"""Together AI — hosted open models (OpenAI-compatible), plus embeddings."""

from __future__ import annotations

from .chat import _openai_compat_embedder, _openai_compat_llm

together_llm = _openai_compat_llm(
    env_prefix="TOGETHER",
    default_model="meta-llama/Llama-3.3-70B-Instruct-Turbo",
    default_base_url="https://api.together.xyz/v1",
)

together_embedder = _openai_compat_embedder(
    env_prefix="TOGETHER",
    default_model="BAAI/bge-large-en-v1.5",
    default_base_url="https://api.together.xyz/v1",
)
