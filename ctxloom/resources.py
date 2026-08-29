from __future__ import annotations

from typing import Any

from .providers import EmbeddingProvider, LLMProvider
from .sources import Source


class RuntimeResources:
    def __init__(
        self,
        llm: LLMProvider | None = None,
        embedder: EmbeddingProvider | None = None,
        sources: dict[str, Source] | None = None,
        **additional: Any,
    ):
        self.llm = llm
        self.embedder = embedder
        self.sources = sources or {}
        self.additional = additional

    def get_source(self, source_id: str) -> Source | None:
        return self.sources.get(source_id)

    def set(self, name: str, value: Any) -> None:
        self.additional[name] = value

    def get(self, name: str) -> Any:
        return self.additional.get(name)
