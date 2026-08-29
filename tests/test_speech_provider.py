"""Speech: TTS (audio/speech) and STT (audio/transcriptions), OpenAI-compatible."""

import asyncio

import httpx
from ctxloom.providers import (
    OpenAICompatSpeech,
    OpenAICompatTranscriber,
    speech_from_env,
    transcriber_from_env,
)


def test_speech_synthesize_bytes_and_auth():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        import json

        seen["body"] = json.loads(request.content)
        return httpx.Response(200, content=b"\xff\xf3audio")

    provider = OpenAICompatSpeech(
        api_key="sk-tts",
        transport=httpx.MockTransport(handler),
    )
    audio = asyncio.run(provider.synthesize("hello, agent", speed=1.1))
    assert audio == b"\xff\xf3audio"
    assert seen["auth"] == "Bearer sk-tts"
    assert seen["url"].endswith("/audio/speech")
    assert seen["body"]["input"] == "hello, agent"
    assert seen["body"]["voice"] == "alloy"
    assert seen["body"]["speed"] == 1.1


def test_speech_voice_overridable():
    provider = OpenAICompatSpeech(
        api_key="k",
        voice="nova",
        transport=httpx.MockTransport(lambda req: httpx.Response(200, content=b"x")),
    )
    assert provider.voice == "nova"


def test_transcriber_multipart_and_text():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["ctype"] = request.headers.get("content-type", "")
        return httpx.Response(200, json={"text": "hello world"})

    provider = OpenAICompatTranscriber(
        api_key="sk-stt",
        transport=httpx.MockTransport(handler),
    )
    text = asyncio.run(provider.transcribe(b"\x00audio", language="en"))
    assert text == "hello world"
    assert seen["url"].endswith("/audio/transcriptions")
    assert "multipart/form-data" in seen["ctype"]


def test_transcriber_groq_endpoint_docs():
    provider = transcriber_from_env(
        api_key="grok",
        base_url="https://api.groq.com/openai/v1",
        model="whisper-large-v3-turbo",
    )
    assert provider is not None
    assert provider.base_url == "https://api.groq.com/openai/v1"
    assert provider.model == "whisper-large-v3-turbo"


def test_speech_env_factory():
    import os

    saved = {
        k: os.environ.get(k) for k in ("SPEECH_API_KEY", "SPEECH_MODEL", "SPEECH_VOICE")
    }
    try:
        os.environ["SPEECH_API_KEY"] = "k1"
        os.environ["SPEECH_MODEL"] = "gpt-4o-mini-tts"
        os.environ["SPEECH_VOICE"] = "ash"
        provider = speech_from_env()
    finally:
        for k in saved:
            if saved[k] is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = saved[k]
    assert provider is not None
    assert provider.voice == "ash"
    assert provider.model == "gpt-4o-mini-tts"
