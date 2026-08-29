"""App-domain text utilities: the Russian stemmer (repair) + English scorer.

These are not framework core, but application-level utilities: the price catalog
and the lexical user search rely on language morphology. The Russian stemmer
serves the Russian `repair` demo; `english_kw_score` serves the English
`knowledge` chat.
"""

from __future__ import annotations

import re

_WORD = re.compile(r"[\wа-яё]{2,}")

_EN_WORD = re.compile(r"[a-z]{2,}")

_EN_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "the",
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
        "into",
        "off",
        "out",
        "over",
        "under",
        "about",
        "up",
        "down",
        "after",
        "before",
        "during",
        "between",
        "through",
        "against",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "has",
        "have",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "can",
        "could",
        "should",
        "how",
        "what",
        "why",
        "which",
        "who",
        "whom",
        "when",
        "where",
        "this",
        "that",
        "these",
        "those",
        "it",
        "its",
        "he",
        "him",
        "his",
        "she",
        "her",
        "they",
        "them",
        "their",
        "we",
        "us",
        "our",
        "you",
        "your",
        "i",
        "me",
        "my",
        "not",
        "no",
        "yes",
        "but",
        "so",
        "then",
        "than",
        "too",
        "very",
        "just",
        "also",
        "because",
        "as",
        "if",
        "much",
        "many",
        "more",
        "most",
    }
)

_STEM_SUFFIXES = (
    "аться",
    "иться",
    "ами",
    "ями",
    "ой",
    "ий",
    "ый",
    "ое",
    "ее",
    "ить",
    "ать",
    "ять",
    "ом",
    "ем",
    "ам",
    "ям",
    "ия",
    "ию",
    "ией",
    "ых",
    "их",
    "ая",
    "яя",
    "у",
    "ю",
    "о",
    "а",
    "е",
    "ы",
    "и",
    "й",
)


def stem(word: str) -> str:
    """Truncates common inflectional suffixes of a Russian word.

    «аутентификацию» and «аутентификация» must match where
    embedders are not needed.
    """
    w = word.lower()
    changed = True
    while changed:
        changed = False
        for suffix in _STEM_SUFFIXES:
            if len(w) - len(suffix) >= 3 and w.endswith(suffix):
                w = w[: -len(suffix)]
                changed = True
                break
    return w


def stem_words(text: str) -> set[str]:
    """Set of word stems in the text (Latin and Cyrillic)."""
    return {stem(t) for t in _WORD.findall(text.lower())}


def stem_score(text: str, query: str) -> float:
    """Coverage of query stems by text stems (0..1), without embedders."""
    query_stems = {stem(t) for t in _WORD.findall(query.lower()) if not t.isdigit()}
    if not query_stems:
        return 0.0
    text_stems = stem_words(text)
    hits = sum(1 for s in query_stems if s in text_stems)
    return hits / len(query_stems)


def english_kw_score(text: str, query: str) -> float:
    """Coverage of the (stop-word-free) English query terms by the text (0..1).

    Neutral keyword matching for the English `knowledge` demo (§8, §67): no
    stemmer, just exact terms minus the common function words, so «how to set
    up authentication?» resolves only to the authentication page.
    """
    words = {w for w in _EN_WORD.findall(text.casefold()) if w not in _EN_STOPWORDS}
    terms = {t for t in _EN_WORD.findall(query.casefold()) if t not in _EN_STOPWORDS}
    if not terms:
        return 0.0
    return sum(1 for t in terms if t in words) / len(terms)
