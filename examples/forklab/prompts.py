"""forklab prompts — the model must know the domain it works in (§68).

Built with the core `PromptTemplate`: declared variables, strict rendering
(a missing var is a KeyError, never a silent `format` leak). Both prompts carry
the *topic* and the exact *question* of the live `Question` artifact, so the
wording and synthesis stages share the same understanding of the product.
"""

from __future__ import annotations

from ctxloom import PromptTemplate

_WORDING = PromptTemplate(
    """You are a research assistant in the domain of {topic}.
You formulate one concise finding sentence from a document snippet, for the
research question: "{question}".

Rules:
- the finding must speak directly to the question;
- one sentence; no hedging; no new facts; no numbers that are not in the snippet;
- the source citation is handled by the system — never invent it."""
)

_SYNTHESIS = PromptTemplate(
    """You are the lead analyst for a product question in the
domain of {topic}. Two competing research branches investigated the question:
"{question}". Write the final answer based on the branch-tagged findings.

Rules:
- weigh findings by their scores; prefer the strongest branch for the conclusion,
  but acknowledge conflicts between the branches;
- cite only the given sources; add no facts;
- be self-contained — the reader has not seen the branches."""
)


def wording_system(*, topic: str, question: str) -> str:
    """The wording stage: a researcher who knows the topic and the question."""
    return _WORDING.render(topic=topic, question=question)


def synthesis_system(*, topic: str, question: str) -> str:
    """The synthesis stage: a lead analyst over the merged branches."""
    return _SYNTHESIS.render(topic=topic, question=question)


__all__ = ["synthesis_system", "wording_system"]
