"""New vendor factories for embeddings/speech/transcription (§ providers
review): right base_url, env key, auth, and passthrough overrides — the
same checks tests/test_vendor_factories.py runs for the chat factories."""

import os

from ctxloom.providers import (
    fireworks_embedder,
    groq_transcriber,
    nvidia_embedder,
    openrouter_embedder,
    openrouter_speech,
    qwen_embedder,
    together_embedder,
)

# factory → (env key, expected base_url)
EMBEDDER_FACTORIES = [
    (openrouter_embedder, "OPENROUTER_API_KEY", "https://openrouter.ai/api/v1"),
    (together_embedder, "TOGETHER_API_KEY", "https://api.together.xyz/v1"),
    (fireworks_embedder, "FIREWORKS_API_KEY", "https://api.fireworks.ai/inference/v1"),
    (
        qwen_embedder,
        "QWEN_API_KEY",
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
    ),
    (nvidia_embedder, "NVIDIA_API_KEY", "https://integrate.api.nvidia.com/v1"),
]


def test_embedder_factories_build_provider():
    for factory, env_key, base_url in EMBEDDER_FACTORIES:
        saved = os.environ.get(env_key)
        os.environ[env_key] = "key-1"
        try:
            embedder = factory()
        finally:
            os.environ.pop(env_key, None)
            if saved is not None:
                os.environ[env_key] = saved
        assert embedder is not None, factory.__name__
        assert embedder.api_key == "key-1", factory.__name__
        assert embedder.base_url == base_url, factory.__name__
        assert embedder._headers["Authorization"] == "Bearer key-1", factory.__name__


def test_embedder_factory_forwards_extra_overrides():
    embedder = openrouter_embedder(api_key="k", timeout=42.0, retry_attempts=1)
    assert embedder._timeout == 42.0
    assert embedder.retry_attempts == 1


def test_groq_transcriber_builds_provider():
    saved = os.environ.get("GROQ_API_KEY")
    os.environ["GROQ_API_KEY"] = "groq-key"
    try:
        transcriber = groq_transcriber()
    finally:
        os.environ.pop("GROQ_API_KEY", None)
        if saved is not None:
            os.environ["GROQ_API_KEY"] = saved
    assert transcriber.api_key == "groq-key"
    assert transcriber.base_url == "https://api.groq.com/openai/v1"
    assert transcriber.model == "whisper-large-v3-turbo"


def test_openrouter_speech_builds_provider_with_default_voice():
    speech = openrouter_speech(api_key="or-key")
    assert speech.api_key == "or-key"
    assert speech.base_url == "https://openrouter.ai/api/v1"
    assert speech.voice == "alloy"
    assert speech.model == "openai/gpt-4o-mini-tts"


def test_factory_names_are_readable():
    """factory.__name__ matches the module attribute name (help()/tracebacks
    show the right thing, not a generic `factory`)."""
    assert openrouter_embedder.__name__ == "openrouter_embedder"
    assert together_embedder.__name__ == "together_embedder"
    assert groq_transcriber.__name__ == "groq_transcriber"
    assert openrouter_speech.__name__ == "openrouter_speech"
