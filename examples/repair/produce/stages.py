"""repair produce — the six pipeline stages (§71).

Each stage is its own Produce with a deterministic guard on `Project.stage`:
collect (facts → designs) → design_choice (pick) → plan (LLM + geometry) →
estimate (catalog, no LLM) → final_approval (HITL gate) → assistant (open-ended
post-approval). Routing follows the project's stage field — the runtime/wake
model builds the links from the artifact state, without a manual graph.
"""

from __future__ import annotations

from typing import Any

from ctxloom import (
    Context,
    InterruptPatch,
    Patch,
    PendingQuestion,
    Produce,
    structured_llm,
)
from ctxloom.artifacts import Artifact
from ctxloom.events import Event
from ctxloom.recipes import changed_fields

from ..models import AssistantReply, Project, ProjectInfo, UserMsg
from ..services.estimate import build_estimate, qa_budget_warning
from ..services.facts import FACT_LABELS, REQUIRED_FACTS
from ..services.fast import fast_reply
from ..services.geometry import ensure_geometry
from ..services.rollback import rollback_target
from .common import (
    _APPROVE_RE,
    _BUDGET_COMPLAINT,
    _approval_text,
    _assistant_context,
    _conversation_text,
    _downstream_resets,
    _extract_info,
    _latest_user_msg,
    _parse_pick,
    _project_artifact,
    _reply,
    _update_project,
)
from .design import _make_design_options
from .plan import _make_plan

# --- collect stage -----------------------------------------------------------


class CollectStage(Produce[Project]):
    """Extracts facts; once all the required ones are present — designs and design_choice."""

    artifact_type = Project

    async def produce(
        self,
        context: Context,
        inputs: list[Artifact[Any]],
        event: Event | None = None,
    ) -> Patch | None:
        if _project_artifact(context) is None:
            return Patch().create(Project())
        project_art = _project_artifact(context)
        assert project_art is not None
        project = project_art.data
        if project.stage != "collect":
            return None
        msg = _latest_user_msg(context)
        if msg is None or msg.id == project.handled_msg:
            return None
        context.announce("Думаю…", kind="status")
        fast = fast_reply(msg.data.text)
        if fast is not None:
            return Patch.merge_existing_patch(
                _update_project(project_art, {"handled_msg": msg.id}),
                _reply(context, msg.id, fast),
            )

        info = ensure_geometry(
            await _extract_info(context, msg.data.text, project.info)
        )
        missing = [f for f in REQUIRED_FACTS if getattr(info, f) is None]
        if missing:
            labeled = ", ".join(FACT_LABELS[f] for f in missing)
            return Patch.merge_existing_patch(
                _update_project(project_art, {"info": info, "handled_msg": msg.id}),
                _reply(
                    context,
                    msg.id,
                    f"Уточните, пожалуйста: {labeled}.",
                ),
            )

        options = await _make_design_options(context, info)
        if options is None:
            return Patch.merge_existing_patch(
                _update_project(project_art, {"info": info, "handled_msg": msg.id}),
                _reply(
                    context,
                    msg.id,
                    "Не удалось подобрать варианты дизайна. Попробуйте ещё раз "
                    "или сформулируйте иначе (например, «предложи варианты»).",
                ),
            )
        previews = "\n".join(
            f"{i + 1}. {o.name} — {o.description}" for i, o in enumerate(options)
        )
        return Patch.merge_existing_patch(
            _update_project(
                project_art,
                {
                    "info": info,
                    "design_options": options,
                    "stage": "design_choice",
                    "handled_msg": msg.id,
                },
            ),
            _reply(
                context,
                msg.id,
                f"Выберите вариант:\n{previews}",
                images=[o.preview for o in options if o.preview],
            ),
        )


# --- design_choice stage -------------------------------------------------------


class PickStage(Produce[Project]):
    """Parses the user's choice → plan."""

    artifact_type = Project

    async def produce(
        self,
        context: Context,
        inputs: list[Artifact[Any]],
        event: Event | None = None,
    ) -> Patch | None:
        project_art = _project_artifact(context)
        if project_art is None or project_art.data.stage != "design_choice":
            return None
        project = project_art.data
        msg = _latest_user_msg(context)
        if msg is None or msg.id == project.handled_msg:
            return None
        context.announce("Думаю…", kind="status")
        pick = _parse_pick(msg.data.text.strip(), project.design_options)
        if pick is None:
            return await _handle_style_change(
                context, project_art, project, msg, project.info
            )
        return Patch.merge_existing_patch(
            _update_project(
                project_art,
                {
                    "design_choice": pick.name,
                    "palette": pick.palette,
                    "stage": "plan",
                    "handled_msg": msg.id,
                    "plan": [],
                    "estimate": None,
                },
            ),
            _reply(context, msg.id, f"Отлично, «{pick.name}». Составляю план…"),
        )


# --- plan / estimate / final_approval stages (deterministic steps) ------------


class PlanStage(Produce[Project]):
    """Plan (LLM + geometry) → estimate."""

    artifact_type = Project

    async def produce(
        self,
        context: Context,
        inputs: list[Artifact[Any]],
        event: Event | None = None,
    ) -> Patch | None:
        project_art = _project_artifact(context)
        if (
            project_art is None
            or project_art.data.stage != "plan"
            or project_art.data.plan
        ):
            return None
        project = project_art.data
        steps = await _make_plan(context, project)
        return _update_project(project_art, {"plan": steps, "stage": "estimate"})


class EstimateStage(Produce[Project]):
    """Estimate — deterministically, via the catalog (no LLM) → final_approval."""

    artifact_type = Project

    async def produce(
        self,
        context: Context,
        inputs: list[Artifact[Any]],
        event: Event | None = None,
    ) -> Patch | None:
        project_art = _project_artifact(context)
        if project_art is None or project_art.data.stage != "estimate":
            return None
        project = project_art.data
        if project.estimate is not None:
            return None
        catalog = context.resources.get("catalog")
        if catalog is None:
            return None
        context.announce("Считаю смету…", kind="status")
        estimate = build_estimate(project.plan, catalog)
        estimate.warnings.extend(qa_budget_warning(estimate, project.info.budget))
        return _update_project(
            project_art, {"estimate": estimate, "stage": "final_approval"}
        )


class ApprovalStage(Produce[Project]):
    """HITL gate (§60): immediately asks the approval question; the answer → assistant or a rebuild."""

    artifact_type = Project

    async def produce(
        self,
        context: Context,
        inputs: list[Artifact[Any]],
        event: Event | None = None,
    ) -> Patch | None:
        project_art = _project_artifact(context)
        if project_art is None or project_art.data.stage != "final_approval":
            return None
        project = project_art.data
        msg = _latest_user_msg(context)

        pending = [p for p in context.pending_questions() if p.data.kind == "approval"]
        if not pending:
            # entering the stage: ask the question immediately, without waiting for a new message
            if msg is not None and msg.id != project.handled_msg:
                return Patch.merge_existing_patch(
                    Patch().create(
                        PendingQuestion(
                            question=_approval_text(project), kind="approval"
                        )
                    ),
                    _reply(context, msg.id, _approval_text(project), kind="approval"),
                    _update_project(project_art, {"handled_msg": msg.id}),
                )
            return Patch().create(
                PendingQuestion(question=_approval_text(project), kind="approval")
            )

        # the user answered the approval question
        if msg is None or msg.id == project.handled_msg:
            return None
        question_art = pending[0]
        answer = msg.data.text.strip()
        context.announce("Думаю…", kind="status")
        resolved = InterruptPatch().answer(question_art, answer)
        if _APPROVE_RE.match(answer):
            return Patch.merge_existing_patch(
                resolved,
                _update_project(
                    project_art,
                    {
                        "approved": True,
                        "stage": "assistant",
                        "handled_msg": msg.id,
                    },
                ),
                _reply(
                    context,
                    msg.id,
                    "Отлично! План и смета утверждены. Теперь могу помогать "
                    "по ходу ремонта: этапы, материалы, цены.",
                ),
            )

        # Anything that is not «да» is a request to change/clarify: extract the edits
        # and rebuild. On a budget/expense complaint, rebuild from the "plan" stage
        # (materials define the estimate), not just the estimate.
        new_info = await _extract_info(context, msg.data.text, project.info)
        changed = changed_fields(project.info, new_info)
        target = rollback_target(changed)
        if not changed and _BUDGET_COMPLAINT.search(msg.data.text):
            target = "plan"
        updates: dict[str, Any] = _downstream_resets(target)
        updates.update(
            {
                "info": ensure_geometry(new_info),
                "stage": target,
                "handled_msg": "",
            }
        )
        # no separate reply: the rebuild will pass and ApprovalStage will show
        # the updated proposal again (the same msg.id gets overwritten by it).
        return Patch.merge_existing_patch(
            resolved, _update_project(project_art, updates)
        )


# --- assistant stage ------------------------------------------------------------


class AssistantStage(Produce[Project]):
    """Open-ended dialogue after approval."""

    artifact_type = Project

    async def produce(
        self,
        context: Context,
        inputs: list[Artifact[Any]],
        event: Event | None = None,
    ) -> Patch | None:
        project_art = _project_artifact(context)
        if project_art is None or project_art.data.stage != "assistant":
            return None
        project = project_art.data
        msg = _latest_user_msg(context)
        if msg is None or msg.id == project.handled_msg:
            return None
        context.announce("Думаю…", kind="status")
        parts = [
            p
            for p in (
                _assistant_context(project),
                _conversation_text(context, msg.id),
            )
            if p
        ]
        context_text = "\n\n".join(parts)
        user = (
            f"{context_text}\n\nВопрос: {msg.data.text}"
            if context_text
            else msg.data.text
        )
        result = await structured_llm(context, schema=AssistantReply, user=user)
        text = (
            result.text
            if result
            else "План и смета утверждены. Спросите про "
            "этапы работ, материалы или цены из сметы."
        )
        return Patch.merge_existing_patch(
            _reply(context, msg.id, text),
            _update_project(project_art, {"handled_msg": msg.id}),
        )


async def _handle_style_change(
    context: Context,
    project_art: Artifact[Project],
    project: Project,
    msg: Artifact[UserMsg],
    current_info: ProjectInfo,
) -> Patch | None:
    """A message at the choice stage without a number — likely a style/palette change.

    Extract updated facts; if something actually changed — regenerate the
    options (like the rollback "style → design_choice" in REPAIR). Otherwise —
    hint to pick a number.
    """
    text_low = msg.data.text.lower()
    if not any(
        keyword in text_low
        for keyword in (
            "стил",
            "дизайн",
            "палитр",
            "давай",
            "цвет",
            "потолок",
            "стен",
            "пол",
        )
    ):
        return _reply(context, msg.id, "Выберите номер варианта, например: 1")

    new_info = ensure_geometry(
        await _extract_info(context, msg.data.text, current_info)
    )
    if not changed_fields(current_info, new_info):
        return _reply(context, msg.id, "Выберите номер варианта, например: 1")

    context.announce("Обновляю варианты под ваш запрос…", kind="status")
    options = await _make_design_options(context, new_info)
    if options is None:
        return _reply(
            context,
            msg.id,
            "Не удалось обновить варианты. Попробуйте ещё раз.",
        )
    previews = "\n".join(
        f"{i + 1}. {o.name} — {o.description}" for i, o in enumerate(options)
    )
    return Patch.merge_existing_patch(
        _update_project(
            project_art,
            {
                "info": new_info,
                "design_options": options,
                "handled_msg": msg.id,
            },
        ),
        _reply(
            context,
            msg.id,
            f"Обновил варианты:\n{previews}",
            images=[o.preview for o in options if o.preview],
        ),
    )


__all__ = [
    "ApprovalStage",
    "AssistantStage",
    "CollectStage",
    "EstimateStage",
    "PickStage",
    "PlanStage",
    "_handle_style_change",
]
