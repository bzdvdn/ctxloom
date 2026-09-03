"""Retry wiring across provider types: chat/embed/image/speech/video all call
with_retry() the same way (verified in isolation in tests/test_retry.py) —
these check each provider actually plugs into it, using a transport that
fails once (503) then succeeds."""

import asyncio

import httpx
from ctxloom.providers import (
    OpenAICompatEmbedder,
    OpenAICompatProvider,
    embedder_from_env,
)
from ctxloom.providers.image import OpenAICompatImageProvider
from ctxloom.providers.speech import OpenAICompatSpeech, OpenAICompatTranscriber
from ctxloom.providers.video import SoraVideoProvider, VideoResult


def _fail_once_then(ok_response: httpx.Response) -> httpx.MockTransport:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(503, text="try again")
        return ok_response

    transport = httpx.MockTransport(handler)
    transport.calls = calls  # type: ignore[attr-defined]
    return transport


def _no_sleep(monkeypatch):
    async def sleep(*_a, **_kw):
        return None

    monkeypatch.setattr(asyncio, "sleep", sleep)


def test_chat_complete_retries_transient_error(monkeypatch):
    _no_sleep(monkeypatch)
    transport = _fail_once_then(
        httpx.Response(
            200,
            json={"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]},
        )
    )
    provider = OpenAICompatProvider(
        base_url="https://llm.example/v1", model="m", transport=transport
    )
    from ctxloom.providers import LLMRequest, Message

    response = asyncio.run(provider.complete(LLMRequest(messages=[Message.user("hi")])))
    assert response.text == "ok"
    assert transport.calls["n"] == 2  # type: ignore[attr-defined]


def test_embed_retries_transient_error(monkeypatch):
    _no_sleep(monkeypatch)
    transport = _fail_once_then(
        httpx.Response(200, json={"data": [{"index": 0, "embedding": [0.1, 0.2]}]})
    )
    embedder = OpenAICompatEmbedder(
        base_url="https://e.example/v1", transport=transport
    )
    vectors = asyncio.run(embedder.embed(["hi"]))
    assert vectors == [[0.1, 0.2]]
    assert transport.calls["n"] == 2  # type: ignore[attr-defined]


def test_embedder_from_env_forwards_extra_overrides():
    import os

    saved = os.environ.get("EMBEDDER_BASE_URL")
    try:
        os.environ["EMBEDDER_BASE_URL"] = "https://e.example/v1"
        embedder = embedder_from_env(timeout=12.5, retry_attempts=1)
    finally:
        if saved is None:
            os.environ.pop("EMBEDDER_BASE_URL", None)
        else:
            os.environ["EMBEDDER_BASE_URL"] = saved
    assert embedder is not None
    assert embedder._timeout == 12.5
    assert embedder.retry_attempts == 1


def test_image_generate_retries_transient_error(monkeypatch):
    _no_sleep(monkeypatch)
    transport = _fail_once_then(
        httpx.Response(200, json={"data": [{"b64_json": "aGVsbG8="}]})
    )
    provider = OpenAICompatImageProvider(
        base_url="https://img.example/v1", transport=transport
    )
    blob = asyncio.run(provider.generate("a cat"))
    assert blob == b"hello"
    assert transport.calls["n"] == 2  # type: ignore[attr-defined]


def test_speech_synthesize_retries_transient_error(monkeypatch):
    _no_sleep(monkeypatch)
    transport = _fail_once_then(httpx.Response(200, content=b"\x00audio"))
    provider = OpenAICompatSpeech(
        base_url="https://tts.example/v1", transport=transport
    )
    audio = asyncio.run(provider.synthesize("hello"))
    assert audio == b"\x00audio"
    assert transport.calls["n"] == 2  # type: ignore[attr-defined]


def test_transcribe_retries_transient_error(monkeypatch):
    _no_sleep(monkeypatch)
    transport = _fail_once_then(httpx.Response(200, json={"text": "hello world"}))
    provider = OpenAICompatTranscriber(
        base_url="https://stt.example/v1", transport=transport
    )
    text = asyncio.run(provider.transcribe(b"\x00fakeaudio"))
    assert text == "hello world"
    assert transport.calls["n"] == 2  # type: ignore[attr-defined]


def test_video_fetch_retries_transient_error(monkeypatch):
    _no_sleep(monkeypatch)
    transport = _fail_once_then(
        httpx.Response(
            200,
            json={
                "id": "v1",
                "status": "completed",
                "output": {"url": "https://cdn.example/v.mp4"},
            },
        )
    )
    provider = SoraVideoProvider(api_key="sk", transport=transport)
    result = asyncio.run(provider.fetch("v1"))
    assert result.status == "completed"
    assert transport.calls["n"] == 2  # type: ignore[attr-defined]


def test_poll_survives_transient_fetch_failures_within_timeout(monkeypatch):
    """poll() must not abort on a fetch() that still raises after its own
    internal retry — it should wait for the next interval and try again."""
    _no_sleep(monkeypatch)
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        # Fail every request for the first 4 calls (more than with_retry's
        # own 3 attempts inside fetch()), then succeed.
        if calls["n"] <= 4:
            return httpx.Response(503, text="down")
        return httpx.Response(
            200,
            json={
                "id": "v1",
                "status": "completed",
                "output": {"url": "https://cdn.example/v.mp4"},
            },
        )

    provider = SoraVideoProvider(api_key="sk", transport=httpx.MockTransport(handler))
    result = asyncio.run(provider.poll("v1", timeout=100, interval=0))
    assert result.status == "completed"
    assert calls["n"] > 4  # outlasted fetch()'s own internal retry budget


def test_poll_gives_up_after_timeout_with_only_failures(monkeypatch):
    """If fetch() never succeeds before the deadline, poll() returns an
    honest failed VideoResult instead of raising out of a best-effort poll."""
    _no_sleep(monkeypatch)

    def always_down(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="down")

    provider = SoraVideoProvider(
        api_key="sk", transport=httpx.MockTransport(always_down)
    )

    # Deadline check happens after the first fetch attempt; timeout=0 means
    # the very first (failed) poll iteration already exceeds it.
    result = asyncio.run(provider.poll("v1", timeout=0, interval=0))
    assert isinstance(result, VideoResult)
    assert result.status == "failed"
    assert result.error is not None
