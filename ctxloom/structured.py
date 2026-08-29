from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Generic, TypeVar

from pydantic import BaseModel, ValidationError

from .context import Context
from .providers import LLMRequest, Message

logger = logging.getLogger(__name__)

TModel = TypeVar("TModel", bound=BaseModel)

SYSTEM_STRUCTURED = (
    "You produce structured output. Reply with a single JSON object only, "
    "no commentary, no code fences."
)


def _extract_json(text: str) -> str | None:
    """Extracts the first balanced JSON object from the model text.

    Local models often add text/code fences around JSON — a tolerant
    parser (§67: parsing is not the LLM's job).
    """
    text = text.strip()
    text = re.sub(r"^```(?:json)?", "", text, flags=re.MULTILINE).rstrip("`").strip()
    try:
        start = text.index("{")
    except ValueError:
        return None
    depth = 0
    in_string = False
    escaped = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def parse_structured(text: str, schema: type[TModel]) -> TModel | None:
    """Tolerant parsing of an LLM response into a pydantic schema."""
    for candidate in (text, _extract_json(text)):
        if not candidate:
            continue
        try:
            return schema.model_validate_json(candidate)
        except ValidationError:
            try:
                return schema.model_validate(json.loads(candidate))
            except (ValueError, ValidationError):
                continue
    return None


async def structured_llm(
    context: Context,
    *,
    schema: type[TModel],
    system: str = SYSTEM_STRUCTURED,
    user: str,
    attempts: int = 2,
) -> TModel | None:
    """Single LLM call against a schema: JSON + tolerant parse + retry.

    Returns `schema` or None (not enough resources / the model did not return valid JSON).
    Deterministic logic (JSON, retry) stays in code; the LLM only reasons (§9, §67).
    """
    llm = context.resources.llm
    if llm is None:
        return None
    instruction = f"Reply with a single JSON object matching this schema:\n{schema.model_json_schema()}"

    def _request(text: str) -> LLMRequest:
        return LLMRequest(
            messages=[
                Message(role="system", content=system),
                Message(role="user", content=text),
            ],
            temperature=0.0,
            response_format={"type": "json_object"},
            max_tokens=2048,
        )

    request = _request(f"{instruction}\n\n{user}")
    total = max(attempts, 1)
    for attempt in range(total):
        try:
            response = await llm.complete(request)
        except Exception:
            if attempt + 1 < total:
                await asyncio.sleep(0.4 * (attempt + 1))  # backoff on network failures
                request = _request(
                    f"{instruction}\n\n{user}\n\n"
                    "The previous request failed. Return a single strict JSON object only."
                )
                continue
            return None  # provider/network failed — honest fallback
        parsed = parse_structured(response.text, schema)
        if parsed is not None:
            return parsed
        logger.debug(
            "structured_llm parse failed (attempt %s): %.160r",
            attempt + 1,
            response.text,
        )
        if attempt + 1 < total:
            request = _request(
                f"{instruction}\n\n{user}\n\n"
                "Previous reply was not valid JSON. Return a single strict JSON object only."
            )
    return None


class StructuredLLM(Generic[TModel]):
    """A reusable structured call: a fixed schema + system, varying only `user`.

    Build a role once, use it wherever the same struct is needed:

        extract_facts = StructuredLLM(schema=Facts, system=SYSTEM_EXTRACTOR)
        facts = await extract_facts.call(context, user="Summarize this page: …")

    All deterministic logic (JSON extraction, retries, backoff) is delegated to
    `structured_llm` (§67); the object only carries the fixed parts.
    """

    def __init__(
        self,
        schema: type[TModel],
        *,
        system: str = SYSTEM_STRUCTURED,
        attempts: int = 2,
    ):
        self.schema = schema
        self.system = system
        self.attempts = attempts

    async def call(self, context: Context, user: str) -> TModel | None:
        return await structured_llm(
            context,
            schema=self.schema,
            system=self.system,
            user=user,
            attempts=self.attempts,
        )
