"""Anthropic — Messages API (not OpenAI-compatible: a separate contract)."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from .contracts import LLMProvider, LLMRequest, LLMResponse, LLMResponseChunk


class AnthropicProvider(LLMProvider):
    """Provider for the Anthropic Messages API (/v1/messages, x-api-key).

    `response_format` does not exist in Anthropic — structured output is obtained
    via plain JSON in the text (the tolerant parse_structured covers this).
    """

    def __init__(
        self,
        api_key: str,
        model: str = "claude-3-5-sonnet-latest",
        base_url: str = "https://api.anthropic.com/v1",
        timeout: float = 90.0,
        transport: Any | None = None,
        extra_headers: dict[str, str] | None = None,
        max_tokens_default: int = 4096,
    ):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._max_tokens_default = max_tokens_default
        self._headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
            **(extra_headers or {}),
        }
        self._transport = transport
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self._timeout,
                transport=self._transport,
                headers=self._headers,
            )
        return self._client

    def _payload(self, request: LLMRequest, stream: bool) -> dict[str, Any]:
        system = "\n\n".join(m.content for m in request.messages if m.role == "system")
        messages = [
            {"role": m.role, "content": m.content}
            for m in request.messages
            if m.role in ("user", "assistant")
        ]
        if not messages:
            messages = [{"role": "user", "content": ""}]
        payload: dict[str, Any] = {
            "model": request.extra.get("model") or self.model,
            "max_tokens": request.max_tokens or self._max_tokens_default,
            "temperature": request.temperature,
            "messages": messages,
            "stream": stream,
        }
        if system:
            payload["system"] = system
        if request.stop:
            payload["stop_sequences"] = request.stop
        for key, value in request.extra.items():
            if key != "model":
                payload[key] = value
        return payload

    async def complete(self, request: LLMRequest) -> LLMResponse:
        response = await self._get_client().post(
            f"{self.base_url}/messages",
            json=self._payload(request, stream=False),
        )
        response.raise_for_status()
        data = response.json()
        text = "".join(
            block.get("text", "")
            for block in data.get("content", [])
            if block.get("type") == "text"
        )
        return LLMResponse(
            text=text,
            raw=data,
            finish_reason=data.get("stop_reason"),
            usage=data.get("usage", {}),
        )

    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMResponseChunk]:
        async with self._get_client().stream(
            "POST",
            f"{self.base_url}/messages",
            json=self._payload(request, stream=True),
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[len("data:") :].strip()
                if not data or data == "[DONE]":
                    continue
                try:
                    blob = json.loads(data)
                except ValueError:
                    continue
                if blob.get("type") == "content_block_delta":
                    delta = blob.get("delta", {})
                    text = delta.get("text")
                    if text:
                        yield LLMResponseChunk(text=text)

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None


def anthropic_llm(
    api_key: str | None = None,
    model: str = "claude-3-5-sonnet-latest",
    **kwargs: Any,
) -> AnthropicProvider | None:
    """Builds an Anthropic provider (key from ANTHROPIC_API_KEY)."""
    if api_key is None:
        import os

        api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return None
    return AnthropicProvider(api_key=api_key, model=model, **kwargs)
