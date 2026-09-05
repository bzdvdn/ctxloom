"""Shared fixtures for the knowledge scenarios — resources, fixture paths,
and the stub LLM used by the record-replay scenario."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path

from ctxloom.providers import LLMProvider, LLMRequest, LLMResponse, LLMResponseChunk
from ctxloom.resources import RuntimeResources

from ..chat import build_resources

#: Committed once `research_answer_against_the_model` is recorded — a small
#: JSONL "cassette" of the real model's request/response pairs (§55).
FIXTURE = Path(__file__).resolve().parent / "data" / "gpu_cost.jsonl"

GPU_COST_QUESTION = "how much does gpu cost in total?"


def resources(llm: LLMProvider | None = None) -> RuntimeResources:
    return build_resources(llm=llm)


def load_recorded_model(path: Path) -> str:
    first_line = path.read_text(encoding="utf-8").splitlines()[0]
    return str(json.loads(first_line)["model"])


class ModelStub(LLMProvider):
    """Carries only the `.model` string `ReplayLLM` needs to key its cache —
    never actually called in `mode='replay'`."""

    def __init__(self, model: str) -> None:
        self.model = model

    async def complete(self, request: LLMRequest) -> LLMResponse:  # pragma: no cover
        raise AssertionError("replay must not fall through to a live call")

    async def stream(  # pragma: no cover
        self, request: LLMRequest
    ) -> AsyncIterator[LLMResponseChunk]:
        for _ in ():
            yield _
        raise AssertionError("replay must not fall through to a live call")
