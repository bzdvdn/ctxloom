import asyncio
import base64
import json

import httpx
from ctxloom.providers.image import OpenAICompatImageProvider

PNG = b"\x89PNG\r\n\x1a\n" + b"x" * 16


def _provider(**kwargs) -> OpenAICompatImageProvider:
    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        seen["url"] = str(request.url)
        return httpx.Response(
            200,
            json={"data": [{"b64_json": base64.b64encode(PNG).decode()}]},
        )

    seen: dict = {}
    provider = OpenAICompatImageProvider(
        api_key="img-key",
        transport=httpx.MockTransport(handler),
        **kwargs,
    )
    return provider, seen


def test_image_generate_defaults_from_provider():
    provider, seen = _provider(size="1024x1024", quality="standard")
    asyncio.run(provider.generate("a cat"))
    assert seen["body"]["model"] == "gpt-image-1"
    assert seen["body"]["n"] == 1
    assert seen["body"]["size"] == "1024x1024"
    assert seen["body"]["quality"] == "standard"


def test_image_generate_per_call_overrides_defaults():
    provider, seen = _provider(size="1024x1024", n=1)
    asyncio.run(provider.generate("a cat", size="512x512", n=2, style="vivid"))
    assert seen["body"]["size"] == "512x512"
    assert seen["body"]["n"] == 2
    assert seen["body"]["style"] == "vivid"


def test_image_generate_omits_unset_size_and_quality():
    provider, seen = _provider()
    asyncio.run(provider.generate("a cat"))
    assert "size" not in seen["body"]
    assert "quality" not in seen["body"]


def test_image_generate_returns_bytes():
    provider, seen = _provider()
    data = asyncio.run(provider.generate("a cat"))
    assert data == PNG
