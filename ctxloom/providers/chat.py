"""Chat and embeddings: OpenAI-compatible providers (OpenAI, Ollama, vLLM,
Mistral, OpenRouter) and factories from env."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from .contracts import (
    EmbeddingProvider,
    LLMProvider,
    LLMRequest,
    LLMResponse,
    LLMResponseChunk,
    auth_value,
)


class OpenAICompatProvider(LLMProvider):
    """OpenAI-compatible provider: OpenAI, Ollama, vLLM, LM Studio, OpenRouter.

    Auth is fully configurable because vendors disagree:
      - header name:  `Authorization` (default), `X-Api-Key`, etc.
      - key scheme:   `Bearer` (default), `OAuth`, `api-key`, or `None` (raw key).
    `proxy` (a URL) is passed to the httpx client for corporate networks.
    `transport` can receive an httpx transport for tests (MockTransport).
    """

    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        model: str | None = None,
        timeout: float = 60.0,
        transport: Any | None = None,
        extra_headers: dict[str, str] | None = None,
        extra_body: dict[str, Any] | None = None,
        proxy: str | None = None,
        auth_header: str = "Authorization",
        auth_scheme: str | None = "Bearer",
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self._timeout = timeout
        self._extra_body = dict(extra_body or {})
        self._headers = dict(extra_headers or {})
        if api_key:
            self._headers.setdefault(auth_header, auth_value(api_key, auth_scheme))
        self._transport = transport
        self._proxy = proxy
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self._timeout,
                transport=self._transport,
                headers=self._headers,
                proxy=self._proxy,
            )
        return self._client

    def _payload(self, request: LLMRequest, stream: bool) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "messages": [
                {"role": m.role, "content": m.content} for m in request.messages
            ],
            "temperature": request.temperature,
            "stream": stream,
        }
        model = request.extra.get("model") or self.model
        if model is not None:
            payload["model"] = model
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens
        if request.stop:
            payload["stop"] = request.stop
        if request.response_format:
            payload["response_format"] = request.response_format
        payload.update(self._extra_body)
        # arbitrary fields (e.g., OpenRouter: {"reasoning": {"enabled": false}})
        for key, value in request.extra.items():
            if key != "model":
                payload[key] = value
        return payload

    async def complete(self, request: LLMRequest) -> LLMResponse:
        response = await self._get_client().post(
            f"{self.base_url}/chat/completions",
            json=self._payload(request, stream=False),
        )
        response.raise_for_status()
        data = response.json()
        choice = data["choices"][0]
        content = choice.get("message", {}).get("content") or ""
        return LLMResponse(
            text=content,
            raw=data,
            finish_reason=choice.get("finish_reason"),
            usage=data.get("usage", {}),
        )

    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMResponseChunk]:
        async with self._get_client().stream(
            "POST",
            f"{self.base_url}/chat/completions",
            json=self._payload(request, stream=True),
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[len("data:") :].strip()
                if data == "[DONE]":
                    break
                if not data:
                    continue
                chunk_ = json.loads(data)
                delta = chunk_["choices"][0].get("delta", {})
                text = delta.get("content")
                if text:
                    yield LLMResponseChunk(text=text)

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None


class OpenAICompatEmbedder(EmbeddingProvider):
    """OpenAI-compatible embedding generator (OpenAI, Mistral, OpenRouter)."""

    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        model: str = "text-embedding-3-small",
        timeout: float = 60.0,
        transport: Any | None = None,
        proxy: str | None = None,
        auth_header: str = "Authorization",
        auth_scheme: str | None = "Bearer",
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self._timeout = timeout
        self._headers = {"Content-Type": "application/json"}
        if api_key:
            self._headers[auth_header] = auth_value(api_key, auth_scheme)
        self._transport = transport
        self._proxy = proxy
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self._timeout,
                transport=self._transport,
                headers=self._headers,
                proxy=self._proxy,
            )
        return self._client

    async def embed(self, texts: list[str]) -> list[list[float]]:
        response = await self._get_client().post(
            f"{self.base_url}/embeddings",
            json={"model": self.model, "input": texts},
        )
        response.raise_for_status()
        data = response.json()
        rows = sorted(data["data"], key=lambda item: item["index"])
        embeddings = [row["embedding"] for row in rows]
        if len(embeddings) != len(texts):
            return []  # API returned fewer rows than requested — honestly empty
        return embeddings

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None


def _network_knobs(
    prefix: str, overrides: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Provider kwargs for proxy/auth from env (`<PREFIX>_PROXY` /
    `_AUTH_HEADER` / `_AUTH_SCHEME`) or explicit overrides.

    Returns only the knobs that are actually configured, so a provider's own
    default (e.g. Gemini's `x-goog-api-key`) is respected when nothing is set.
    An empty `AUTH_SCHEME` means the raw key (no prefix).
    """
    import os

    ov = overrides or {}
    knobs: dict[str, Any] = {}

    proxy = ov.get("proxy")
    if proxy is None:
        proxy = os.getenv(f"{prefix}_PROXY")
    if proxy is not None:
        knobs["proxy"] = proxy or None

    header = ov.get("auth_header")
    if header is None:
        header = os.getenv(f"{prefix}_AUTH_HEADER")
    if header is not None and header != "":
        knobs["auth_header"] = header

    scheme = ov.get("auth_scheme")
    if scheme is None:
        scheme = os.getenv(f"{prefix}_AUTH_SCHEME")
    if scheme is not None:
        knobs["auth_scheme"] = None if scheme == "" else scheme

    return knobs


def llm_from_env(**overrides: Any) -> OpenAICompatProvider | None:
    """Builds a provider from OPENAI_BASE_URL/OPENAI_API_KEY/OPENAI_MODEL.

    OPENAI_EXTRA_BODY (JSON) is added to every request — e.g., for
    OpenRouter: '{"reasoning": {"enabled": false}}'. Optional network/auth
    knobs: OPENAI_PROXY (URL), OPENAI_AUTH_HEADER (default Authorization),
    OPENAI_AUTH_SCHEME (Bearer by default; set to "api-key", "OAuth" or an
    empty value for providers that want the raw key). Returns None if
    BASE_URL is not set — the app runs on its fallbacks.
    """
    import os

    base_url = overrides.get("base_url") or os.getenv("OPENAI_BASE_URL")
    if not base_url:
        return None
    extra_body: dict[str, Any] | None = overrides.get("extra_body")
    if extra_body is None:
        raw = os.getenv("OPENAI_EXTRA_BODY")
        extra_body = json.loads(raw) if raw else None
    return OpenAICompatProvider(
        base_url=base_url,
        api_key=overrides.get("api_key") or os.getenv("OPENAI_API_KEY") or None,
        model=overrides.get("model") or os.getenv("OPENAI_MODEL") or None,
        extra_body=extra_body,
        **_network_knobs("OPENAI", overrides),
    )


def embedder_from_env(**overrides: Any) -> OpenAICompatEmbedder | None:
    """Builds an embedder from EMBEDDER_BASE_URL/EMBEDDER_API_KEY/EMBEDDER_MODEL.

    Optional knobs: EMBEDDER_PROXY, EMBEDDER_AUTH_HEADER, EMBEDDER_AUTH_SCHEME.
    """
    import os

    base_url = overrides.get("base_url") or os.getenv("EMBEDDER_BASE_URL")
    if not base_url:
        return None
    api_key = overrides.get("api_key") or os.getenv("EMBEDDER_API_KEY")
    model = overrides.get("model") or os.getenv("EMBEDDER_MODEL")
    return OpenAICompatEmbedder(
        base_url=base_url,
        api_key=api_key,
        model=model if isinstance(model, str) else "text-embedding-3-small",
        **_network_knobs("EMBEDDER", overrides),
    )
