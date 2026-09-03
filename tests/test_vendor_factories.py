"""Every OpenAI-compatible vendor factory: right base_url, env key, auth."""

import os

from ctxloom.providers import (
    cerebras_llm,
    github_models_llm,
    groq_llm,
    mistral_llm,
    nvidia_nim_llm,
    perplexity_llm,
    qwen_llm,
    xai_llm,
    zai_llm,
)

# factory → (env key, expected base_url)
FACTORIES = [
    (zai_llm, "ZAI_API_KEY", "https://api.z.ai/api/paas/v4"),
    (cerebras_llm, "CEREBRAS_API_KEY", "https://api.cerebras.ai/v1"),
    (github_models_llm, "GITHUB_TOKEN", "https://models.github.ai/v1"),
    (qwen_llm, "QWEN_API_KEY", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
    (nvidia_nim_llm, "NVIDIA_API_KEY", "https://integrate.api.nvidia.com/v1"),
    (perplexity_llm, "PERPLEXITY_API_KEY", "https://api.perplexity.ai"),
    (groq_llm, "GROQ_API_KEY", "https://api.groq.com/openai/v1"),
    (xai_llm, "XAI_API_KEY", "https://api.x.ai/v1"),
    (mistral_llm, "MISTRAL_API_KEY", "https://api.mistral.ai/v1"),
]


def test_openai_compat_factories_build_provider():
    for factory, env_key, base_url in FACTORIES:
        saved = os.environ.get(env_key)
        os.environ[env_key] = "key-1"
        try:
            provider = factory()
        finally:
            os.environ.pop(env_key, None)
            if saved is not None:
                os.environ[env_key] = saved
        assert provider is not None, factory.__name__
        assert provider.api_key == "key-1"
        assert provider.base_url == base_url, factory.__name__
        assert provider._headers["Authorization"] == "Bearer key-1"


def test_factory_returns_provider_even_without_key():
    """mistral-style: the factory returns a provider (key may be None later)."""
    factory, env_key, _ = FACTORIES[0]
    saved = os.environ.pop(env_key, None)
    try:
        provider = factory(base_url="https://example.test/v1")
    finally:
        if saved is not None:
            os.environ[env_key] = saved
    assert provider is not None
    assert provider.base_url == "https://example.test/v1"
