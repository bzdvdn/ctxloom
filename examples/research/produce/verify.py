"""research verify — deterministic claim verification (§35, §67)."""

from __future__ import annotations

from ctxloom import Artifact, Context, Event, Patch, Produce

from ..models import Claim, Evidence
from .common import split_sentences, token_support


class VerifyClaims(Produce[Claim]):
    """Deterministic verification (§67): a sentence becomes a claim with
    confidence = how much of it the source page supports (§35, §68)."""

    artifact_type = Claim

    async def produce(
        self,
        context: Context,
        inputs: list[Artifact[Evidence]],
        event: Event | None = None,
    ) -> Patch | None:
        evidence_art = context.get(event.artifact_id) if event is not None else None
        if evidence_art is None or not isinstance(evidence_art.data, Evidence):
            return None
        evidence = evidence_art.data
        docs = context.related(evidence_art.id, relation="extracted_from")
        doc_text = docs[0].data.content if docs else ""

        context.announce(
            f"Verifying facts from «{evidence.source}»...",
            kind="status",
            source=evidence.source,
        )
        patch = Patch()
        for i, sentence in enumerate(split_sentences(evidence.text)):
            support = token_support(sentence, doc_text)
            confidence = round(
                min(1.0, (0.3 + 0.7 * support) * 0.6 + 0.4 * (evidence.score or 0.3)),
                2,
            )
            status = (
                "verified"
                if support >= 0.6
                else ("weak" if support >= 0.35 else "unverified")
            )
            claim_id = f"claim:{evidence_art.id}:{i}"
            patch.create(
                Claim(
                    query_id=evidence.query_id,
                    text=sentence,
                    confidence=confidence,
                    status=status,
                ),
                id=claim_id,
            )
            patch.link(claim_id, "derived_from", evidence_art.id)
        return patch
