"""Providers package: contracts + implementations (chat, embeddings, images, fakes).

The app configures the needed providers when initializing resources;
the core public API (`ctxloom`) exports only contracts.
"""

from __future__ import annotations

from typing import Any

from .anthropic import AnthropicProvider, anthropic_llm
from .azure import azure_llm
from .cerebras import cerebras_llm
from .chat import (
    OpenAICompatEmbedder,
    OpenAICompatProvider,
    embedder_from_env,
    llm_from_env,
)
from .contracts import (
    EmbeddingProvider,
    LLMProvider,
    LLMRequest,
    LLMResponse,
    LLMResponseChunk,
    Message,
    Role,
)
from .deepseek import deepseek_llm
from .fake import FakeEmbedder, FakeLLM
from .fireworks import fireworks_embedder, fireworks_llm
from .gemini import GeminiImageProvider, GeminiProvider, gemini_image, gemini_llm
from .github_models import github_models_llm
from .groq import groq_llm, groq_transcriber
from .image import (
    ImageProvider,
    OpenAICompatImageProvider,
    OpenRouterImageProvider,
    image_from_env,
)
from .mistral import mistral_embedder, mistral_llm
from .nvidia import nvidia_embedder, nvidia_nim_llm
from .ollama import ollama_llm
from .openai import openai_embedder, openai_llm
from .openrouter import (
    openrouter_embedder,
    openrouter_image,
    openrouter_llm,
    openrouter_speech,
)
from .perplexity import perplexity_llm
from .qwen import qwen_embedder, qwen_llm
from .speech import (
    OpenAICompatSpeech,
    OpenAICompatTranscriber,
    SpeechProvider,
    TranscriberProvider,
    speech_from_env,
    transcriber_from_env,
)
from .together import together_embedder, together_llm
from .video import (
    LumaVideoProvider,
    OpenRouterVideoProvider,
    RunwayVideoProvider,
    SoraVideoProvider,
    VideoProvider,
    VideoResult,
    video_from_env,
)
from .xai import xai_llm
from .zai import zai_llm


def from_env(**overrides: Any) -> LLMProvider | None:
    """One-call provider selection: `OPENROUTER_API_KEY` first, else a local
    OpenAI-compatible endpoint via `OPENAI_BASE_URL`, else `None` (offline).

    This is the exact two-branch selection every example in this repo hand-
    rolls as a local `build_llm()` (deliberately, per example, so a reader
    sees the wiring — see `examples/*/main.py`); use this instead when you
    just want the common default in your own app without copying that block.
    Overrides (`model`, `max_tokens`, `temperature`, ...) are forwarded to
    whichever provider ends up selected.
    """
    return openrouter_llm(**overrides) or llm_from_env(**overrides)


__all__ = [
    "AnthropicProvider",
    "EmbeddingProvider",
    "FakeEmbedder",
    "FakeLLM",
    "GeminiImageProvider",
    "GeminiProvider",
    "ImageProvider",
    "LLMProvider",
    "LLMRequest",
    "LLMResponse",
    "LLMResponseChunk",
    "LumaVideoProvider",
    "Message",
    "OpenAICompatEmbedder",
    "OpenAICompatImageProvider",
    "OpenAICompatProvider",
    "OpenAICompatSpeech",
    "OpenAICompatTranscriber",
    "OpenRouterImageProvider",
    "OpenRouterVideoProvider",
    "Role",
    "RunwayVideoProvider",
    "SoraVideoProvider",
    "SpeechProvider",
    "TranscriberProvider",
    "VideoProvider",
    "VideoResult",
    "anthropic_llm",
    "azure_llm",
    "cerebras_llm",
    "deepseek_llm",
    "embedder_from_env",
    "fireworks_embedder",
    "fireworks_llm",
    "from_env",
    "gemini_image",
    "gemini_llm",
    "github_models_llm",
    "groq_llm",
    "groq_transcriber",
    "image_from_env",
    "llm_from_env",
    "mistral_embedder",
    "mistral_llm",
    "nvidia_embedder",
    "nvidia_nim_llm",
    "ollama_llm",
    "openai_embedder",
    "openai_llm",
    "openrouter_embedder",
    "openrouter_image",
    "openrouter_llm",
    "openrouter_speech",
    "perplexity_llm",
    "qwen_embedder",
    "qwen_llm",
    "speech_from_env",
    "together_embedder",
    "together_llm",
    "transcriber_from_env",
    "video_from_env",
    "xai_llm",
    "zai_llm",
]
