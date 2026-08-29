"""Shared helpers for the research pipeline (§48, §65).

Routing helpers and the deterministic claim tools used by the extraction,
verification and answer stages. No LLM here — deterministic logic stays in
code (§67).
"""

from __future__ import annotations

import re

from ctxloom import Context, Event

from ..models import ResearchTurn, UserQuery

# How many best-relevance refs to take from all sources (§24).
SCOUT_LIMIT = 5
# How many of the most confident claims to show in the deterministic fallback.
FALLBACK_TOPN = 3

_STOPWORDS = frozenset(
    {
        "the",
        "a",
        "an",
        "and",
        "or",
        "of",
        "to",
        "in",
        "for",
        "on",
        "with",
        "at",
        "by",
        "from",
        "is",
        "are",
        "was",
        "were",
        "be",
        "it",
        "its",
        "this",
        "that",
        "how",
        "what",
        "why",
        "which",
        "does",
        "do",
        "you",
        "we",
        "they",
        "he",
        "she",
        "not",
        "no",
        "but",
        "so",
        "about",
        "as",
    }
)
_SENT_SPLIT_RE = re.compile(r"[.!?]+\s+|\n+")


def user_query(context: Context, event: Event | None) -> UserQuery | None:
    artifact = context.get(event.artifact_id) if event is not None else None
    if artifact is not None and isinstance(artifact.data, UserQuery):
        return artifact.data
    return None


def turn_of(context: Context, event: Event | None) -> ResearchTurn | None:
    artifact = context.get(event.artifact_id) if event is not None else None
    if artifact is not None and isinstance(artifact.data, ResearchTurn):
        return artifact.data
    return None


def split_sentences(text: str) -> list[str]:
    sentences = [s.strip() for s in _SENT_SPLIT_RE.split(text) if s.strip()]
    return sentences or ([text.strip()] if text.strip() else [])


def tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z]{2,}", text.casefold())) - _STOPWORDS


def token_support(claim: str, source: str) -> float:
    """Share of the claim's tokens confirmed in the source text (0..1)."""
    terms = tokens(claim)
    if not terms:
        return 0.0
    source_terms = tokens(source)
    return len(terms & source_terms) / len(terms)
