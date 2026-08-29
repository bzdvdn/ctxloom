"""Produce classes of the demo assistant: all the logic lives here, agents are containers.

Each Produce is a self-contained piece: the artifact type (`artifact_type`) +
`produce(context, inputs, event)`. Here too sits the deterministic routing
«greeting/direct reply vs research» (§67); the LLM is only invoked where
language matters (fact extraction, answer assembly).
"""

from __future__ import annotations

import re
from typing import Any

from ctxloom.artifacts import Artifact
from ctxloom.context import Context
from ctxloom.events import Event
from ctxloom.patches import Patch
from ctxloom.produce import Produce
from ctxloom.sources import SourceRef
from ctxloom.structured import structured_llm

from .models import (
    Answer,
    AnswerBody,
    Calculation,
    ChatReply,
    Claim,
    Evidence,
    ResearchTurn,
    SearchDone,
    Spreadsheet,
    TypedDoc,
    UserQuery,
)

GREETING_RE = re.compile(
    r"^(привет|здравств|добры[йе].*день|добрый вечер|hello|hi|hey|"
    r"good (morning|afternoon|evening))\b",
    re.IGNORECASE,
)
RESEARCH_RE = re.compile(
    r"(как|почему|сколько|стоит|цена|настроить|установить|изменить|"
    r"аутентификац|платформ|инструкц|план|ошибк|каталог|token|gpu|"
    r"how\b|how (much|many)|why\b|what\b|cost|price|configure|install|"
    r"change|authenticat|platform|method|rest|api|pay|invoic|bill\w*|"
    r"monitor|alert|enable|set up|deploy|instruct|plan|error|catalog)",
    re.IGNORECASE,
)
GREETING_TEXT = (
    "Hello! Ask about the product or any documentation question — "
    "I'll find the answer in the docs."
)
# How many of the best-relevance refs to take from all sources (§24).
_SCOUT_LIMIT = 5
# How many of the most relevant fragments to show in the deterministic fallback.
_FALLBACK_TOPN = 3
# How many of the most recent dialog entries to keep in chat memory.
_CONVERSATION_LIMIT = 8


def _conversation_text(context: Context, current_query_id: str) -> str:
    """Chat memory: the previous conversation (without the current turn) via view (§27).

    The `context.view` selection: UserQuery/ChatReply/Answer, excluding the
    current turn (the question itself and its outputs), the last
    `_CONVERSATION_LIMIT` entries.
    """
    view = context.view(
        (UserQuery, ChatReply, Answer),
        condition=lambda a: (
            not (
                a.id == current_query_id
                or getattr(a.data, "query_id", "") == current_query_id
            )
        ),
    )
    ordered = sorted(view.artifacts, key=lambda a: a.created_at)
    recent = ordered[-_CONVERSATION_LIMIT:]
    if not recent:
        return ""
    lines = [
        f"user: {a.data.text}"
        if isinstance(a.data, UserQuery)
        else f"assistant: {a.data.text}"
        for a in recent
    ]
    return "Conversation:\n" + "\n".join(lines)


def _user_query(context: Context, event: Event | None) -> UserQuery | None:
    artifact = context.get(event.artifact_id) if event is not None else None
    if artifact is not None and isinstance(artifact.data, UserQuery):
        return artifact.data
    return None


# --- Claim verification (§35, §36): deterministic confirmation of a fact
# --- against the source document + cross-source contradiction detection.
# --- Fully deterministic, no LLM (§67): the model does not own the truth (§68).

_STOPWORDS = {
    "и",
    "или",
    "в",
    "во",
    "на",
    "с",
    "со",
    "по",
    "для",
    "при",
    "о",
    "об",
    "к",
    "ко",
    "у",
    "то",
    "что",
    "как",
    "это",
    "его",
    "ее",
    "ей",
    "их",
    "он",
    "она",
    "мы",
    "вы",
    "не",
    "же",
    "бы",
    "да",
    "нет",
    "а",
    "но",
    "который",
    "которая",
    "которые",
    "так",
    "чтобы",
    "the",
    "and",
    "or",
    "of",
    "to",
    "in",
    "on",
    "for",
    "with",
    "is",
    "are",
    "was",
    "were",
    "a",
    "an",
    "this",
    "that",
    "what",
    "how",
    "his",
    "her",
    "its",
    "their",
    "he",
    "she",
    "we",
    "you",
    "they",
    "them",
    "not",
    "no",
    "yes",
    "but",
    "so",
    "which",
    "who",
    "about",
    "by",
    "at",
    "from",
    "be",
    "been",
    "being",
    "has",
    "have",
    "had",
    "do",
    "does",
    "did",
    "also",
    "it",
    "as",
}
_NEGATIONS = (
    "не",
    "никогда",
    "нельзя",
    "против",
    "без",
    "вопреки",
    "no",
    "not",
    "never",
    "without",
    "against",
)
_SENT_SPLIT_RE = re.compile(r"[.!?。]+\s+|\n+")
_INTERESTING_COL_RE = re.compile(
    r"(cost|price|spend|amount|usage|gpu_cost|стоим|цена|трат|расход|gpu)",
    re.IGNORECASE,
)


def _claim_tokens(text: str) -> set[str]:
    return set(re.findall(r"[а-яёa-z]{2,}", text.casefold())) - _STOPWORDS


def _token_support(claim: str, source: str) -> float:
    """Share of the claim tokens confirmed in the source text (0..1)."""
    claim_tokens = _claim_tokens(claim)
    if not claim_tokens:
        return 0.0
    source_tokens = _claim_tokens(source)
    return len(claim_tokens & source_tokens) / len(claim_tokens)


def _has_negation(text: str) -> bool:
    lowered = text.casefold()
    return any(neg in lowered for neg in _NEGATIONS)


def _split_sentences(text: str) -> list[str]:
    sentences = [s.strip() for s in _SENT_SPLIT_RE.split(text) if s.strip()]
    return sentences or ([text.strip()] if text.strip() else [])


def _source_doc_of(context: Context, evidence: Artifact[Any]) -> Artifact[Any] | None:
    docs = context.related(evidence.id, relation="extracted_from")
    return docs[0] if docs else None


# --- VerifyClaims: Evidence → Claim (+ cross-claim contradictions) ---


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
        ta, tb = _claim_tokens(a), _claim_tokens(b)
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
        doc = _source_doc_of(context, evidence_art)
        doc_text = doc.data.content if doc is not None else ""

        context.announce(
            f"Verifying facts from «{evidence.source}»...",
            kind="status",
            source=evidence.source,
        )

        # 1) Texts of this Evidence's new claims (§35): sentence → claim.
        new_items: list[tuple[str, str]] = [
            (f"claim:{evidence_art.id}:{i}", sentence)
            for i, sentence in enumerate(_split_sentences(evidence.text))
        ]
        conflicting: set[str] = set()
        for aid, a_text in new_items:
            for bid, b_text in new_items:
                if aid >= bid:
                    continue
                if self._similarity(a_text, b_text) >= 0.5 and _has_negation(
                    a_text
                ) != _has_negation(b_text):
                    conflicting.update({aid, bid})
            # against already-applied claims from other sources (§36)
            for other in context.list_artifacts(Claim):
                if other.data.query_id != evidence.query_id:
                    continue
                if self._similarity(a_text, other.data.text) >= 0.5 and _has_negation(
                    a_text
                ) != _has_negation(other.data.text):
                    conflicting.update({aid, other.id})

        # 2) Patch: create claims (conflict flag already in the data), links and tags.
        patch = Patch()
        for aid, sentence in new_items:
            support = _token_support(sentence, doc_text)
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

        # contradiction links between the new claims
        for i, (aid, a_text) in enumerate(new_items):
            for bid, b_text in new_items[i + 1 :]:
                if self._similarity(a_text, b_text) >= 0.5 and _has_negation(
                    a_text
                ) != _has_negation(b_text):
                    patch.link(aid, "contradicted_by", bid)
                    patch.link(bid, "contradicted_by", aid)
        # contradiction tags on already-existing claims
        for other in context.list_artifacts(Claim):
            if (
                other.id in conflicting
                and other.data.query_id == evidence.query_id
                and not other.data.conflict
            ):
                patch.update_fields(other, conflict=True)
        return patch


# --- Planner: two mutually exclusive outcomes = two Produce (-s) (§48) ---


class PlannerReply(Produce[ChatReply]):
    """ChatReply: greeting / direct reply. None for research questions."""

    artifact_type = ChatReply

    async def produce(
        self,
        context: Context,
        inputs: list[Artifact[UserQuery]],
        event: Event | None = None,
    ) -> Patch | None:
        user = _user_query(context, event)
        if user is None or event is None:
            return None
        text = user.text.strip()
        context.announce("Thinking...", kind="status")

        if GREETING_RE.match(text):
            context.announce("Replying to the greeting", kind="status")
            return Patch().create(
                ChatReply(
                    query_id=event.artifact_id, text=GREETING_TEXT, kind="greeting"
                )
            )

        if RESEARCH_RE.search(text):
            return None  # research branch

        context.announce("Replying from general knowledge", kind="status")
        answer = await structured_llm(
            context,
            schema=AnswerBody,
            user=f"Answer concisely and to the point:\n{text}",
        )
        reply = (
            answer.text.strip()
            if answer
            else "This question doesn't require consulting the documentation."
        )
        return Patch().create(
            ChatReply(query_id=event.artifact_id, text=reply, kind="direct")
        )


class PlannerTurn(Produce[ResearchTurn]):
    """ResearchTurn: for questions that need a source search."""

    artifact_type = ResearchTurn

    async def produce(
        self,
        context: Context,
        inputs: list[Artifact[UserQuery]],
        event: Event | None = None,
    ) -> Patch | None:
        user = _user_query(context, event)
        if user is None or event is None:
            return None
        text = user.text.strip()
        if not RESEARCH_RE.search(text):
            return None
        context.announce("Question requires a documentation search", kind="status")
        return Patch().create(
            ResearchTurn(query_id=event.artifact_id, text=text, status="researching")
        )


# --- SearchScout: fan-out over sources with announce ---


class ScoutSources(Produce[SourceRef]):
    artifact_type = SourceRef

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
        # Idempotency (§42): if the search for this turn is already finished —
        # don't restart the cascade. A re-run would do create-or-refresh of the
        # refs → ARTIFACT_UPDATED → resolver → evidence → evaluator → scout
        # (an infinite loop, tuned down only by the budget).
        if any(
            s.data.query_id == turn.query_id for s in context.list_artifacts(SearchDone)
        ):
            return None
        patch = Patch()
        refs: list[SourceRef] = []
        for source in context.resources.sources.values():
            context.announce(
                f"Searching for information in source «{source.source_id}»...",
                kind="status",
                source=source.source_id,
            )
            found = source.search(turn.text, limit=_SCOUT_LIMIT)
            context.announce(
                f"Found {len(found)} matches in «{source.source_id}»",
                kind="status",
                count=len(found),
                source=source.source_id,
            )
            refs.extend(found)
        # top by relevance across all sources, without weak-match noise
        refs.sort(key=lambda r: r.score or 0.0, reverse=True)
        for ref in refs[:_SCOUT_LIMIT]:
            scoped = ref.model_copy(update={"query_id": turn.query_id})
            patch.create(scoped, id=ref.stable_id())
        # deterministic search-complete marker — signals the evaluator
        # that no more refs will appear (§24)
        patch.create(SearchDone(query_id=turn.query_id), id=f"scouted:{turn.query_id}")
        return patch


# --- Resolver: lazy materialization of a typed document ---


class ResolveRef(Produce[TypedDoc]):
    artifact_type = TypedDoc

    async def produce(
        self,
        context: Context,
        inputs: list[Artifact[SourceRef]],
        event: Event | None = None,
    ) -> Patch | None:
        ref_artifact = context.get(event.artifact_id) if event is not None else None
        if ref_artifact is None or not isinstance(ref_artifact.data, SourceRef):
            return None
        ref = ref_artifact.data
        if ref.metadata.get("structured"):
            return None  # not our branch: spreadsheets go to ResolveTable
        source = context.resources.get_source(ref.source_id)
        if source is None:
            return None
        context.announce(
            f"Reading document «{ref.locator}» from {ref.source_id}...",
            kind="status",
            source=ref.source_id,
            path=ref.locator,
        )
        try:
            content = await source.resolve(ref)
        except Exception:
            return None
        doc_id = f"resolved:{ref.stable_id()}"
        # provenance (§34): TypedDoc —resolved_from→ SourceRef
        return (
            Patch()
            .create(
                TypedDoc(
                    source_id=ref.source_id,
                    path=ref.locator,
                    content=content,
                    query_id=ref.query_id,
                    score=ref.score or 0.0,
                ),
                id=doc_id,
            )
            .link(doc_id, "resolved_from", ref_artifact.id)
        )


# --- EvidenceBuilder: a key fact from the document (schema → fact, §18) ---


class ExtractEvidence(Produce[Evidence]):
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


# --- ResolveTable: lazy materialization of a structured spreadsheet (§29) ---


class ResolveTable(Produce[Spreadsheet]):
    """Spreadsheet: structured data stays structured, not text (§29).

    Fires only for a ref with `metadata.structured` (e.g. a CSV source):
    text documents go to ResolveRef, spreadsheets come here. The resolve result
    is {columns, rows}; provenance: Spreadsheet —materialized_from→ SourceRef.
    """

    artifact_type = Spreadsheet

    async def produce(
        self,
        context: Context,
        inputs: list[Artifact[SourceRef]],
        event: Event | None = None,
    ) -> Patch | None:
        ref_artifact = context.get(event.artifact_id) if event is not None else None
        if ref_artifact is None or not isinstance(ref_artifact.data, SourceRef):
            return None
        ref = ref_artifact.data
        if not ref.metadata.get("structured"):
            return None  # not our branch: text documents go to ResolveRef
        source = context.resources.get_source(ref.source_id)
        if source is None:
            return None
        context.announce(
            f"Reading spreadsheet «{ref.locator}» from {ref.source_id}...",
            kind="status",
            source=ref.source_id,
            path=ref.locator,
        )
        try:
            payload = await source.resolve(ref)
        except Exception:
            return None
        columns = list(payload.get("columns", []))
        rows = [list(r) for r in payload.get("rows", [])]
        sheet_id = f"sheet:{ref.stable_id()}"
        return (
            Patch()
            .create(
                Spreadsheet(
                    source_id=ref.source_id,
                    path=ref.locator,
                    columns=columns,
                    rows=rows,
                    query_id=ref.query_id,
                ),
                id=sheet_id,
            )
            .link(sheet_id, "materialized_from", ref_artifact.id)
        )


# --- CalculateAggregate: deterministic aggregation instead of hallucination (§67) ---

_CALC_INTENT_RE = re.compile(
    r"(суммарн\w*|сумма\w*|итого|сколько[^\n]{0,20}стоит|"
    r"средн\w*|максим\w*|миним\w*|"
    r"sum|total|average|avg|mean|how much[^\n]{0,20}(cost|spend)|"
    r"max|maximum|min|minimum)",
    re.IGNORECASE,
)


def _aggregate_intent(question: str) -> str | None:
    """Which aggregation is requested (sum/mean/max/min), or None (§67)."""
    if not question:
        return None
    matched = _CALC_INTENT_RE.search(question)
    if matched is None:
        return None
    token = matched.group(0).casefold()
    if (
        "суммарн" in token
        or "сумма" in token
        or "итого" in token
        or "стоит" in token
        or "sum" in token
        or "total" in token
        or "cost" in token
        or "spend" in token
    ):
        return "sum"
    if "средн" in token or "average" in token or "avg" in token or "mean" in token:
        return "mean"
    if "максим" in token or "max" in token:
        return "max"
    if "миним" in token or "min" in token:
        return "min"
    return None


def _numeric_column(sheet: Spreadsheet) -> tuple[str | None, list[float]]:
    """The most specific «cost/usage» column; otherwise numeric."""
    candidates = sheet.columns
    matched = [col for col in candidates if _INTERESTING_COL_RE.search(col)]
    # a more specific name (cost_usd vs gpu_cost_usd) is preferred
    chosen = max(matched, key=len, default=None)
    if chosen is None:
        chosen = candidates[0] if candidates else ""
    try:
        idx = sheet.columns.index(chosen)
    except ValueError:
        return None, []
    values: list[float] = []
    for row in sheet.rows:
        if idx >= len(row):
            continue
        raw = row[idx].strip()
        try:
            values.append(float(raw.replace(",", ".")))
        except ValueError:
            continue
    return chosen, values


class CalculateAggregate(Produce[Calculation]):
    """Calculation: computes over the spreadsheet if the question asks for an aggregate (§29, §67).

    Deterministic arithmetic (sum/mean/max/min over the relevant numeric column).
    Provenance: Calculation —derived_from→ Spreadsheet.
    """

    artifact_type = Calculation

    async def produce(
        self,
        context: Context,
        inputs: list[Artifact[Spreadsheet]],
        event: Event | None = None,
    ) -> Patch | None:
        sheet_art = context.get(event.artifact_id) if event is not None else None
        if sheet_art is None or not isinstance(sheet_art.data, Spreadsheet):
            return None
        sheet = sheet_art.data
        question = next(
            (
                t.data.text
                for t in context.list_artifacts(ResearchTurn)
                if t.data.query_id == sheet.query_id
            ),
            "",
        )
        func = _aggregate_intent(question)
        if func is None:
            return None
        column, values = _numeric_column(sheet)
        if column is None or not values:
            return None

        if func == "sum":
            value = sum(values)
            description = f"Sum over column «{column}»"
        elif func == "mean":
            value = sum(values) / len(values)
            description = f"Mean of column «{column}»"
        elif func == "max":
            value = max(values)
            description = f"Maximum of column «{column}»"
        else:
            value = min(values)
            description = f"Minimum of column «{column}»"
        description += f" ({len(values)} rows, {sheet.source_id}:{sheet.path})"
        value = round(value, 2) if isinstance(value, float) else value
        context.announce(
            f"Computing: {description} = {value}",
            kind="status",
            path=sheet.path,
        )
        calc_id = f"calc:{sheet.query_id}:{sheet_art.id}"
        return (
            Patch()
            .create(
                Calculation(
                    query_id=sheet.query_id,
                    description=description,
                    value=value,
                    column=column,
                    rows=len(values),
                ),
                id=calc_id,
            )
            .link(calc_id, "derived_from", sheet_art.id)
        )


# --- ProgressEvaluator: deterministic turn overseer (§24, §69) ---


class EvaluateTurn(Produce[ResearchTurn]):
    """Moves the turn's status when state changes (only to a new status)."""

    artifact_type = ResearchTurn

    TERMINAL = {"answered", "insufficient"}
    _QUERY_CARRIERS = (
        ResearchTurn,
        SourceRef,
        Evidence,
        Claim,
        TypedDoc,
        Spreadsheet,
        Calculation,
        SearchDone,
        Answer,
    )

    @staticmethod
    def _query_id_of(context: Context, event: Event | None) -> str | None:
        """Which query_id caused this event."""
        artifact = context.get(event.artifact_id) if event is not None else None
        if artifact is None:
            return None
        for model in EvaluateTurn._QUERY_CARRIERS:
            if isinstance(artifact.data, model):
                return artifact.data.query_id
        return None

    @staticmethod
    def _next_status(context: Context, query_id: str) -> str | None:
        """Pure function: which status the turn deserves in the current state."""
        refs = [
            r for r in context.list_artifacts(SourceRef) if r.data.query_id == query_id
        ]
        evidences = [
            e for e in context.list_artifacts(Evidence) if e.data.query_id == query_id
        ]
        calculations = [
            c
            for c in context.list_artifacts(Calculation)
            if c.data.query_id == query_id
        ]
        searched = any(
            s.data.query_id == query_id for s in context.list_artifacts(SearchDone)
        )
        answered = any(
            a.data.query_id == query_id for a in context.list_artifacts(Answer)
        )
        # Answer ready: there is document material (evidence) OR a computed
        # result (calculation) against the found refs (§24, §29).
        if answered:
            return "answered"
        if refs and (evidences or calculations):
            return "answerable"
        if searched and not refs:
            return "insufficient"
        return None

    async def produce(
        self,
        context: Context,
        inputs: list[Artifact[ResearchTurn]],
        event: Event | None = None,
    ) -> Patch | None:
        query_id = self._query_id_of(context, event)
        if query_id is None:
            return None
        turns = [
            t
            for t in context.list_artifacts(ResearchTurn)
            if t.data.query_id == query_id
        ]
        if not turns:
            return None
        turn = turns[0]
        if turn.data.status in self.TERMINAL:
            return None
        next_status = self._next_status(context, query_id)
        if next_status is None or next_status == turn.data.status:
            return None
        context.announce(
            f"Research status: {turn.data.status} → {next_status}",
            kind="status",
            query_id=query_id,
        )
        return Patch().update_fields(turn, status=next_status)


# --- AnswerBuilder: projection of all the query's evidence (§17) ---


class BuildAnswer(Produce[Answer]):
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
        # material: verified claims (confidence/status/conflict) (§35, §36)
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
        conversation = _conversation_text(context, query_id)
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
            # without an LLM (or the model gave no valid answer) — an honest fallback (§68):
            # the most confident facts, then calculations, not a concatenation of everything.
            parts: list[str] = []
            top = materials[:_FALLBACK_TOPN]
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
        # provenance (§34): Answer —supported_by→ Evidence (+spreadsheet via calculation)
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
