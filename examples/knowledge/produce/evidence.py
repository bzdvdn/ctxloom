"""knowledge evidence — extraction and deterministic claim verification."""

from __future__ import annotations

from ctxloom import Artifact, Context, Event, Patch, Produce
from ctxloom.structured import structured_llm

from ..models import AnswerBody, Claim, Evidence, TypedDoc
from .common import (
    claim_tokens,
    has_negation,
    source_doc_of,
    split_sentences,
    token_support,
)


class ExtractEvidence(Produce[Evidence]):
    """A key fact from the document (schema → fact, §18)."""

    artifact_type = Evidence

    async def produce(
        self,
        context: Context,
        inputs: list[Artifact[TypedDoc]],
        event: Event | None = None,
    ) -> Patch | None:
        doc_artifact = context.get(event.artifact_id) if event is not None else None
        if doc_artifact is None or not isinstance(doc_artifact.data, TypedDoc):
            return None
        doc = doc_artifact.data
        context.announce(
            f"Extracting key facts from «{doc.path}»...",
            kind="status",
            path=doc.path,
        )
        body = await structured_llm(
            context,
            schema=AnswerBody,
            user=f"Extract a short factual digest from the document:\n{doc.content}",
        )
        text = body.text.strip() if body else " ".join(doc.content.split())[:200]
        evidence_id = f"evidence:{doc.query_id}:{doc.path}"
        # provenance (§34): Evidence —extracted_from→ TypedDoc
        return (
            Patch()
            .create(
                Evidence(
                    query_id=doc.query_id,
                    text=text,
                    source=f"{doc.source_id}:{doc.path}",
                    score=doc.score,
                ),
                id=evidence_id,
            )
            .link(evidence_id, "extracted_from", doc_artifact.id)
        )


class VerifyClaims(Produce[Claim]):
    """Builds verifiable claims from a fact and computes their confirmation (§35).

    Each Evidence sentence → Claim with confidence (by matching against the
    source-document text). Pairs of claims with high similarity and differing
    polarity get a `contradicted_by` link — a contradiction stays a first-class
    state rather than something hidden in a string (§36, §69).
    """

    artifact_type = Claim

    @staticmethod
    def _similarity(a: str, b: str) -> float:
        ta, tb = claim_tokens(a), claim_tokens(b)
        if not ta or not tb:
            return 0.0
        return len(ta & tb) / min(len(ta), len(tb))

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
        doc = source_doc_of(context, evidence_art)
        doc_text = doc.data.content if doc is not None else ""

        context.announce(
            f"Verifying facts from «{evidence.source}»...",
            kind="status",
            source=evidence.source,
        )

        new_items: list[tuple[str, str]] = [
            (f"claim:{evidence_art.id}:{i}", sentence)
            for i, sentence in enumerate(split_sentences(evidence.text))
        ]
        conflicting: set[str] = set()
        for aid, a_text in new_items:
            for bid, b_text in new_items:
                if aid >= bid:
                    continue
                if self._similarity(a_text, b_text) >= 0.5 and has_negation(
                    a_text
                ) != has_negation(b_text):
                    conflicting.update({aid, bid})
            for other in context.list_artifacts(Claim):
                if other.data.query_id != evidence.query_id:
                    continue
                if self._similarity(a_text, other.data.text) >= 0.5 and has_negation(
                    a_text
                ) != has_negation(other.data.text):
                    conflicting.update({aid, other.id})

        patch = Patch()
        for aid, sentence in new_items:
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
            patch.create(
                Claim(
                    query_id=evidence.query_id,
                    text=sentence,
                    confidence=confidence,
                    status=status,
                    conflict=aid in conflicting,
                ),
                id=aid,
            )
            patch.link(aid, "derived_from", evidence_art.id)

        for i, (aid, a_text) in enumerate(new_items):
            for bid, b_text in new_items[i + 1 :]:
                if self._similarity(a_text, b_text) >= 0.5 and has_negation(
                    a_text
                ) != has_negation(b_text):
                    patch.link(aid, "contradicted_by", bid)
                    patch.link(bid, "contradicted_by", aid)
        for other in context.list_artifacts(Claim):
            if (
                other.id in conflicting
                and other.data.query_id == evidence.query_id
                and not other.data.conflict
            ):
                patch.update_fields(other, conflict=True)
        return patch
