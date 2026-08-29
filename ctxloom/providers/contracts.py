"""LLM/embedder provider contracts — clean core, no implementations.

Concrete providers live in the `providers` package (../providers), along with
their env-based factories. Only interfaces live here, so the core does not pull in httpx.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Message:
    role: str
    content: str


@dataclass
class LLMRequest:
    messages: list[Message]
    temperature: float = 0.7
    max_tokens: int | None = None
    stop: list[str] = field(default_factory=list)
    response_format: dict[str, Any] | None = None
    headers: dict[str, str] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMResponse:
    text: str
    raw: Any = None
    finish_reason: str | None = None
    usage: dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMResponseChunk:
    text: str
    finish_reason: str | None = None


class LLMProvider(ABC):
    @abstractmethod
    async def complete(self, request: LLMRequest) -> LLMResponse: ...

    # Deliberately not async: implementations are generators (yield), but the contract is an async iterator.
    @abstractmethod
    def stream(self, request: LLMRequest) -> AsyncIterator[LLMResponseChunk]: ...


class EmbeddingProvider(ABC):
    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]: ...


#: Builds the value of an auth header.


def auth_value(api_key: str, scheme: str | None) -> str:
    """Builds the value of an auth header.

    `scheme=None` sends the raw key (Anthropic's `x-api-key`, and other
    `api-key`-style APIs); a custom scheme (Bearer/OAuth/api-key/Token) formats
    it as `f"{scheme} {api_key}"`. The header *name* is provider's choice
    (`Authorization`, `X-Api-Key`, ...) and is not decided here.
    """
    return api_key if scheme is None else f"{scheme} {api_key}"
