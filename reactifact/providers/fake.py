"""Deterministic fakes for tests and local runs."""

from __future__ import annotations

import hashlib
from collections.abc import AsyncIterator

from .contracts import (
    EmbeddingProvider,
    LLMProvider,
    LLMRequest,
    LLMResponse,
    LLMResponseChunk,
)


class FakeLLM(LLMProvider):
    def __init__(self, response: str = "This is a fake response."):
        self.response = response

    async def complete(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(text=self.response)

    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMResponseChunk]:
        yield LLMResponseChunk(text=self.response)


class FakeEmbedder(EmbeddingProvider):
    def __init__(self, dim: int = 8):
        self.dim = dim

    async def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        for text in texts:
            hash_bytes = hashlib.sha256(text.encode()).digest()
            vec = [float(b) / 255.0 for b in hash_bytes[: self.dim]]
            if len(vec) < self.dim:
                vec.extend([0.0] * (self.dim - len(vec)))
            vectors.append(vec)
        return vectors
