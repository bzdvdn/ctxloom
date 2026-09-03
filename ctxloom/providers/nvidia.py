"""NVIDIA NIM — hosted open models (OpenAI-compatible), plus embeddings."""

from __future__ import annotations

from .chat import _openai_compat_embedder, _openai_compat_llm

nvidia_nim_llm = _openai_compat_llm(
    env_prefix="NVIDIA",
    default_model="meta/llama-3.3-70b-instruct",
    default_base_url="https://integrate.api.nvidia.com/v1",
    name="nvidia_nim_llm",
)

nvidia_embedder = _openai_compat_embedder(
    env_prefix="NVIDIA",
    default_model="nvidia/llama-3.2-nv-embedqa-1b-v2",
    default_base_url="https://integrate.api.nvidia.com/v1",
)
