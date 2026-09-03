"""Qwen (Alibaba DashScope) — chat (OpenAI-compatible), plus embeddings."""

from __future__ import annotations

from .chat import _openai_compat_embedder, _openai_compat_llm

qwen_llm = _openai_compat_llm(
    env_prefix="QWEN",
    default_model="qwen-plus",
    default_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
)

qwen_embedder = _openai_compat_embedder(
    env_prefix="QWEN",
    default_model="text-embedding-v2",
    default_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
)
