"""Image generation: OpenRouter (/images), factory from env.

Not part of the core public API — the app wires `ImageProvider`
into resources if needed.
"""

from __future__ import annotations

import base64
from abc import ABC, abstractmethod
from typing import Any

import httpx


class ImageProvider(ABC):
    """Image generation (e.g., OpenRouter /images)."""

    @abstractmethod
    async def generate(self, prompt: str, **params: Any) -> bytes | None:
        """Returns PNG/JPEG bytes or None if generation failed."""
        ...


class OpenRouterImageProvider(ImageProvider):
    """OpenAI-compatible image generator: POST {base}/images → b64_json."""

    def __init__(
        self,
        base_url: str = "https://openrouter.ai/api/v1",
        api_key: str | None = None,
        model: str = "google/gemini-3-pro-create-image-plus",
        timeout: float = 90.0,
        transport: Any | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self._timeout = timeout
        self._transport = transport
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            self._client = httpx.AsyncClient(
                timeout=self._timeout, transport=self._transport, headers=headers
            )
        return self._client

    async def generate(self, prompt: str, **params: Any) -> bytes | None:
        payload: dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "n": params.get("n", 1),
        }
        for key in ("aspect_ratio", "resolution", "output_format"):
            if key in params:
                payload[key] = params[key]
        response = await self._get_client().post(
            f"{self.base_url}/images", json=payload
        )
        response.raise_for_status()
        data = response.json()
        first = (data.get("data") or [None])[0]
        if not first or not first.get("b64_json"):
            return None
        return base64.b64decode(first["b64_json"])

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None


def image_from_env(**overrides: Any) -> OpenRouterImageProvider | None:
    """Builds an image generator from IMAGE_* / OPENROUTER_*. Returns
    None if no key is set — the app skips renders."""
    import os

    api_key = (
        overrides.get("api_key")
        or os.getenv("IMAGE_API_KEY")
        or os.getenv("OPENROUTER_API_KEY")
    )
    if not api_key:
        return None
    return OpenRouterImageProvider(
        base_url=os.getenv("IMAGE_BASE_URL") or "https://openrouter.ai/api/v1",
        api_key=api_key,
        model=os.getenv("IMAGE_MODEL", "google/gemini-3-pro-create-image-plus"),
    )
