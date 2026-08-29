"""knowledge lifecycle — deterministic turn overseer and the answer builder."""

from __future__ import annotations

from ctxloom import Artifact, Context, Event, Patch, Produce
from ctxloom.recipes import StatusMachine
from ctxloom.sources import SourceRef
from ctxloom.structured import structured_llm

from ..models import (
    Answer,
    AnswerBody,
    Calculation,
    Claim,
    Evidence,
    ResearchTurn,
    SearchDone,
    Spreadsheet,
)
from .common import FALLBACK_TOPN, conversation_text


class EvaluateTurn(StatusMachine[ResearchTurn]):
    """Moves the turn's status when state changes (deterministic, §24, §69)."""

    artifact_type = ResearchTurn
    terminal = frozenset({"answered", "insufficient"})

    def next_status(self, context: Context, key: str) -> str | None:
        """Pure function: which status the turn deserves in the current state."""
        refs = [r for r in context.list_artifacts(SourceRef) if r.data.query_id == key]
        evidences = [
            e for e in context.list_artifacts(Evidence) if e.data.query_id == key
        ]
        calculations = [
            c for c in context.list_artifacts(Calculation) if c.data.query_id == key
        ]
        searched = any(
            s.data.query_id == key for s in context.list_artifacts(SearchDone)
        )
        answered = any(a.data.query_id == key for a in context.list_artifacts(Answer))
        if answered:
            return "answered"
        if refs and (evidences or calculations):
            return "answerable"
        if searched and not refs:
            return "insufficient"
        return None

    def on_transition(
        self, context: Context, key: str, old_status: str, new_status: str
    ) -> None:
        context.announce(
            f"Research status: {old_status} → {new_status}",
            kind="status",
            query_id=key,
        )


class BuildAnswer(Produce[Answer]):
    """Projection of all the query's evidence into an answer (§17, §34)."""

    artifact_type = Answer

    async def produce(
        self,
        context: Context,
        inputs: list[Artifact[ResearchTurn]],
        event: Event | None = None,
    ) -> Patch | None:
        turn_artifact = context.get(event.artifact_id) if event is not None else None
        if turn_artifact is None or not isinstance(turn_artifact.data, ResearchTurn):
            return None
        turn = turn_artifact.data
        if turn.status != "answerable":
            return None
        query_id = turn.query_id

        evidences = [
            e for e in context.list_artifacts(Evidence) if e.data.query_id == query_id
        ]
        claims = [
            c for c in context.list_artifacts(Claim) if c.data.query_id == query_id
        ]
        calculations = [
            c
            for c in context.list_artifacts(Calculation)
            if c.data.query_id == query_id
        ]
        if not evidences and not calculations:
            return None

        context.announce(
            f"Assembling the answer from {len(evidences)} facts and "
            f"{len(calculations)} calculation(s)...",
            kind="status",
            count=len(evidences) + len(calculations),
        )
        source_by_evidence = {e.id: e.data.source for e in evidences}
        materials: list[tuple[str, str]] = []
        if claims:
            claims.sort(key=lambda c: c.data.confidence, reverse=True)
            for claim in claims:
                linked = context.related(claim.id, relation="derived_from")
                source = source_by_evidence.get(linked[0].id) if linked else "?"
                status = "conflict" if claim.data.conflict else claim.data.status
                meta = f"{source} [conf {claim.data.confidence:g}, {status}]"
                materials.append((meta, claim.data.text))
        else:
            evidences.sort(key=lambda e: e.data.score, reverse=True)
            materials.extend(
                (f"{e.data.source} [score {e.data.score:g}]", e.data.text)
                for e in evidences
            )
        for calc in calculations:
            materials.append(("calc", f"{calc.data.description} = {calc.data.value}"))

        conflicts = [c for c in claims if c.data.conflict]
        material_lines = "\n".join(f"- {meta}: {text}" for meta, text in materials)
        if conflicts and claims:
            material_lines += (
                f"\n\n⚠ Contradictions found between claims (n={len(conflicts)})."
            )
        question = next(
            (
                t.data.text
                for t in context.list_artifacts(ResearchTurn)
                if t.data.query_id == query_id
            ),
            "",
        )
        conversation = conversation_text(context, query_id)
        prompt = "Assemble a coherent answer to the question based on the facts."
        if conversation:
            prompt += f"\n\n{conversation}"
        prompt += f"\nQuestion: {question}\nFacts:\n{material_lines}"
        body = await structured_llm(context, schema=AnswerBody, user=prompt)
        sources = [e.data.source for e in evidences] + [
            f"{c.data.source_id}:{c.data.path}"
            for c in context.list_artifacts(Spreadsheet)
            if c.data.query_id == query_id
        ]
        if body is not None:
            text = body.text.strip()
        else:
            # Without an LLM (or the model gave no valid answer) — an honest
            # fallback (§68): the most confident facts, then calculations.
            parts: list[str] = []
            top = materials[:FALLBACK_TOPN]
            for meta, mtext in top:
                if meta == "calc" or meta.startswith("calc"):
                    parts.append(f"• Calc: {mtext}")
                else:
                    parts.append(f"• {meta}: {mtext}")
            calc_note = (
                (
                    " Also: "
                    + "; ".join(
                        f"{c.data.description} = {c.data.value}" for c in calculations
                    )
                )
                if calculations
                else ""
            )
            text = (
                "Failed to assemble a coherent answer. "
                "Here are the most relevant documentation fragments and calculations:"
                "\n\n" + "\n\n".join(parts) + calc_note
            )
        context.announce(
            f"Done: {len(sources)} sources",
            kind="status",
            done=True,
            sources=sources,
        )
        answer_id = f"answer:{query_id}"
        patch = Patch().create(
            Answer(query_id=query_id, text=text, sources=sources),
            id=answer_id,
        )
        for evidence_art in evidences:
            patch.link(answer_id, "supported_by", evidence_art.id)
        for calc in context.list_artifacts(Calculation):
            if calc.data.query_id == query_id:
                patch.link(answer_id, "supported_by", calc.id)
        return patch
