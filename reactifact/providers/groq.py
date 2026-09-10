"""Groq — fast inference (OpenAI-compatible), plus Whisper transcription."""

from __future__ import annotations

from .chat import _openai_compat_llm
from .speech import _openai_compat_transcriber

groq_llm = _openai_compat_llm(
    env_prefix="GROQ",
    default_model="llama-3.3-70b-versatile",
    default_base_url="https://api.groq.com/openai/v1",
)

groq_transcriber = _openai_compat_transcriber(
    env_prefix="GROQ",
    default_model="whisper-large-v3-turbo",
    default_base_url="https://api.groq.com/openai/v1",
)
