"""Providers package: contracts + implementations (chat, embeddings, images, fakes).

The app configures the needed providers when initializing resources;
the core public API (`ctxloom`) exports only contracts.
"""

from __future__ import annotations

from .anthropic import AnthropicProvider, anthropic_llm
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
)
from .deepseek import deepseek_llm
from .fake import FakeEmbedder, FakeLLM
from .image import ImageProvider, OpenRouterImageProvider, image_from_env
from .mistral import mistral_embedder, mistral_llm
from .ollama import ollama_llm
from .openai import openai_embedder, openai_llm
from .openrouter import openrouter_image, openrouter_llm

__all__ = [
    "AnthropicProvider",
    "EmbeddingProvider",
    "FakeEmbedder",
    "FakeLLM",
    "ImageProvider",
    "LLMProvider",
    "LLMRequest",
    "LLMResponse",
    "LLMResponseChunk",
    "Message",
    "OpenAICompatEmbedder",
    "OpenAICompatProvider",
    "OpenRouterImageProvider",
    "anthropic_llm",
    "deepseek_llm",
    "embedder_from_env",
    "image_from_env",
    "llm_from_env",
    "mistral_embedder",
    "mistral_llm",
    "ollama_llm",
    "openai_embedder",
    "openai_llm",
    "openrouter_image",
    "openrouter_llm",
]
