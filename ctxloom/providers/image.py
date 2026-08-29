"""Image generation: OpenRouter (/images), factory from env.

Not part of the core public API — the app wires `ImageProvider`
into resources if needed.
"""

from __future__ import annotations

import base64
from abc import ABC, abstractmethod
from typing import Any

import httpx

from .chat import _network_knobs
from .contracts import auth_value


class ImageProvider(ABC):
    """Image generation (e.g., OpenRouter /images)."""

    @abstractmethod
    async def generate(self, prompt: str, **params: Any) -> bytes | None:
        """Returns PNG/JPEG bytes or None if generation failed."""
        ...


class OpenAICompatImageProvider(ImageProvider):
    """OpenAI-compatible image generator (OpenAI images, OpenRouter, Azure, ...).

    POSTs to `{base}/images` and decodes the `b64_json` of the first result.
    Auth header/scheme and proxy are configurable like the chat providers.
    """

    def __init__(
        self,
        base_url: str = "https://api.openai.com/v1",
        api_key: str | None = None,
        model: str = "gpt-image-1",
        timeout: float = 120.0,
        transport: Any | None = None,
        proxy: str | None = None,
        auth_header: str = "Authorization",
        auth_scheme: str | None = "Bearer",
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self._timeout = timeout
        self._transport = transport
        self._proxy = proxy
        self._auth_header = auth_header
        self._auth_scheme = auth_scheme
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers[self._auth_header] = auth_value(self.api_key, self._auth_scheme)
            self._client = httpx.AsyncClient(
                timeout=self._timeout,
                transport=self._transport,
                headers=headers,
                proxy=self._proxy,
            )
        return self._client

    async def generate(self, prompt: str, **params: Any) -> bytes | None:
        payload: dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "n": params.get("n", 1),
        }
        for key in (
            "aspect_ratio",
            "resolution",
            "output_format",
            "size",
            "quality",
            "style",
            "background",
            "moderation",
        ):
            if key in params:
                payload[key] = params[key]
        response = await self._get_client().post(
            f"{self.base_url}/images", json=payload
        )
        response.raise_for_status()
        data = response.json()
        first = (data.get("data") or [None])[0]
        if not first:
            return None
        if first.get("b64_json"):
            return base64.b64decode(first["b64_json"])
        url = first.get("url")
        if url:
            fetched = await self._get_client().get(url)
            fetched.raise_for_status()
            return fetched.content
        return None

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None


# Back-compat alias (the previous name, now that the provider is vendor-neutral).
OpenRouterImageProvider = OpenAICompatImageProvider


def image_from_env(**overrides: Any) -> OpenAICompatImageProvider | None:
    """Builds an image generator from IMAGE_* / OPENROUTER_*. Returns
    None if no key is set — the app skips renders. Optional knobs:
    IMAGE_PROXY, IMAGE_AUTH_HEADER, IMAGE_AUTH_SCHEME."""
    import os

    api_key = (
        overrides.get("api_key")
        or os.getenv("IMAGE_API_KEY")
        or os.getenv("OPENROUTER_API_KEY")
    )
    if not api_key:
        return None
    merged = {**_network_knobs("IMAGE", overrides), **overrides}
    return OpenAICompatImageProvider(
        base_url=os.getenv("IMAGE_BASE_URL") or "https://openrouter.ai/api/v1",
        api_key=api_key,
        model=os.getenv("IMAGE_MODEL", "google/gemini-3-pro-create-image-plus"),
        **merged,
    )
