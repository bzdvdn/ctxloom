"""Speech: text-to-speech (synthesis) and speech-to-text (transcription).

Both are OpenAI-compatible (`/audio/speech` and `/audio/transcriptions`), so
they also cover vendors that mirror OpenAI (Groq Whisper, Azure Speech, ...)
by pointing `base_url` at their OpenAI-compatible endpoint. Auth header/scheme
and proxy are configurable like every other provider.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import httpx

from .chat import _network_knobs
from .contracts import auth_value


class SpeechProvider(ABC):
    """Text-to-speech: returns audio bytes from text."""

    @abstractmethod
    async def synthesize(self, text: str, **params: Any) -> bytes:
        """Synthesizes speech; returns audio bytes (mp3/opus/wav/aac...)."""


class TranscriberProvider(ABC):
    """Speech-to-text: returns a transcript from audio bytes."""

    @abstractmethod
    async def transcribe(self, audio: bytes, **params: Any) -> str:
        """Transcribes audio; returns the text."""


class Connectable:
    """Shared HTTP client builder for the OpenAI-compatible speech endpoints.

    No global Content-Type: httpx sets it per request (JSON for `json=`,
    multipart boundary for `files=`) — forcing it here would break the
    multipart transcription upload.
    """

    def build_client(
        self,
        timeout: float,
        transport: Any,
        proxy: str | None,
        api_key: str | None,
        auth_header: str,
        auth_scheme: str | None,
    ) -> httpx.AsyncClient:
        headers: dict[str, str] = {}
        if api_key:
            headers[auth_header] = auth_value(api_key, auth_scheme)
        return httpx.AsyncClient(
            timeout=timeout, transport=transport, headers=headers, proxy=proxy
        )


class OpenAICompatSpeech(SpeechProvider):
    """TTS via `{base}/audio/speech` (OpenAI tts-1/gpt-4o-mini-tts, Azure...)."""

    def __init__(
        self,
        base_url: str = "https://api.openai.com/v1",
        api_key: str | None = None,
        model: str = "tts-1",
        voice: str = "alloy",
        timeout: float = 60.0,
        transport: Any | None = None,
        proxy: str | None = None,
        auth_header: str = "Authorization",
        auth_scheme: str | None = "Bearer",
        extra_params: dict[str, Any] | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.voice = voice
        self._timeout = timeout
        self._extra = dict(extra_params or {})
        self._transport = transport
        self._proxy = proxy
        self._auth_header = auth_header
        self._auth_scheme = auth_scheme
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = Connectable().build_client(
                self._timeout,
                self._transport,
                self._proxy,
                self.api_key,
                self._auth_header,
                self._auth_scheme,
            )
        return self._client

    async def synthesize(self, text: str, **params: Any) -> bytes:
        payload: dict[str, Any] = {
            "model": params.get("model") or self.model,
            "input": text,
            "voice": params.get("voice") or self.voice,
        }
        for key in ("response_format", "speed", "instructions"):
            if params.get(key):
                payload[key] = params[key]
        payload.update(self._extra)
        response = await self._get_client().post(
            f"{self.base_url}/audio/speech", json=payload
        )
        response.raise_for_status()
        return response.content

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None


class OpenAICompatTranscriber(TranscriberProvider):
    """STT via `{base}/audio/transcriptions` (OpenAI Whisper, Groq Whisper...)."""

    def __init__(
        self,
        base_url: str = "https://api.openai.com/v1",
        api_key: str | None = None,
        model: str = "whisper-1",
        timeout: float = 120.0,
        transport: Any | None = None,
        proxy: str | None = None,
        auth_header: str = "Authorization",
        auth_scheme: str | None = "Bearer",
        mime_type: str = "audio/webm",
        filename: str = "audio.webm",
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self._timeout = timeout
        self._transport = transport
        self._proxy = proxy
        self._auth_header = auth_header
        self._auth_scheme = auth_scheme
        self._mime_type = mime_type
        self._filename = filename
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = Connectable().build_client(
                self._timeout,
                self._transport,
                self._proxy,
                self.api_key,
                self._auth_header,
                self._auth_scheme,
            )
        return self._client

    async def transcribe(self, audio: bytes, **params: Any) -> str:
        model = params.get("model") or self.model
        files = {
            "file": (params.get("filename") or self._filename, audio, self._mime_type)
        }
        data: dict[str, str] = {"model": model}
        for key in ("language", "prompt", "response_format"):
            if params.get(key):
                data[key] = str(params[key])
        response = await self._get_client().post(
            f"{self.base_url}/audio/transcriptions",
            files=files,
            data=data,
        )
        response.raise_for_status()
        body = response.json()
        if isinstance(body, dict):
            return str(body.get("text", ""))
        return str(body)

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None


def _factory_extra(overrides: dict[str, Any], skip: tuple[str, ...]) -> dict[str, Any]:
    return {k: v for k, v in overrides.items() if k not in skip}


def speech_from_env(**overrides: Any) -> OpenAICompatSpeech | None:
    """Builds a TTS provider from env (SPEECH_* or OPENAI_*).

    Keys: SPEECH_BASE_URL / SPEECH_API_KEY / SPEECH_MODEL / SPEECH_VOICE plus
    the usual SPEECH_PROXY / SPEECH_AUTH_HEADER / SPEECH_AUTH_SCHEME.
    """
    import os

    api_key = (
        overrides.get("api_key")
        or os.getenv("SPEECH_API_KEY")
        or os.getenv("OPENAI_API_KEY")
    )
    if not api_key:
        return None
    merged = {
        **_network_knobs("SPEECH", overrides),
        **_factory_extra(overrides, ("api_key", "base_url", "model", "voice")),
    }
    return OpenAICompatSpeech(
        base_url=overrides.get("base_url")
        or os.getenv("SPEECH_BASE_URL")
        or "https://api.openai.com/v1",
        api_key=api_key,
        model=overrides.get("model") or os.getenv("SPEECH_MODEL") or "tts-1",
        voice=overrides.get("voice") or os.getenv("SPEECH_VOICE") or "alloy",
        **merged,
    )


def transcriber_from_env(**overrides: Any) -> OpenAICompatTranscriber | None:
    """Builds an STT provider from env (TRANSCRIBER_* or OPENAI_*).

    Keys: TRANSCRIBER_BASE_URL / TRANSCRIBER_API_KEY / TRANSCRIBER_MODEL plus
    the usual TRANSCRIBER_PROXY / TRANSCRIBER_AUTH_HEADER / AUTH_SCHEME.
    Point TRANSCRIBER_BASE_URL at api.groq.com/openai/v1 and set
    TRANSCRIBER_MODEL=whisper-large-v3-turbo for Groq Whisper.
    """
    import os

    api_key = (
        overrides.get("api_key")
        or os.getenv("TRANSCRIBER_API_KEY")
        or os.getenv("OPENAI_API_KEY")
    )
    if not api_key:
        return None
    merged = {
        **_network_knobs("TRANSCRIBER", overrides),
        **_factory_extra(overrides, ("api_key", "base_url", "model")),
    }
    return OpenAICompatTranscriber(
        base_url=overrides.get("base_url")
        or os.getenv("TRANSCRIBER_BASE_URL")
        or "https://api.openai.com/v1",
        api_key=api_key,
        model=overrides.get("model") or os.getenv("TRANSCRIBER_MODEL") or "whisper-1",
        **merged,
    )
