"""Repair pipeline stages as Produce classes (§71).

`RepairFlow` reacts to UserMsg and Project; each stage is its own Produce
with a deterministic guard. Routing follows `Project.stage` — the runtime/wake
model builds links from the artifacts, without a manual graph.
"""

from __future__ import annotations

import asyncio
import logging
import re
import uuid
from typing import Any

from ctxloom import (
    InterruptPatch,
    Patch,
    PendingQuestion,
    Produce,
    structured_llm,
)
from ctxloom.artifacts import Artifact
from ctxloom.context import Context
from ctxloom.events import Event
from examples.textutil import stem_words

from .fallbacks import fallback_options, fallback_plan
from .image_prompt import build_image_prompt
from .models import (
    AssistantReply,
    ChatReply,
    DesignOption,
    DesignOptions,
    PlanStep,
    Project,
    ProjectInfo,
    RepairPlan,
    UserMsg,
)
from .services import (
    FACT_LABELS,
    REQUIRED_FACTS,
    build_estimate,
    changed_fields,
    ensure_geometry,
    fast_reply,
    geometry_text,
    qa_budget_warning,
    rollback_target,
)

logger = logging.getLogger(__name__)

_PICK_NUMBER = re.compile(r"^\s*(\d+)\s*$")
_APPROVE_RE = re.compile(r"^(да|подтвержд|согласен|ок|yes)\b", re.IGNORECASE)
# A cost/budget complaint — rebuild cheaper from the "plan" stage, not the estimate.
_BUDGET_COMPLAINT = re.compile(
    r"бюджет|дорог|вышел за бюджет|превыш|уложи|дешевле|много|дорого",
    re.IGNORECASE,
)


def _latest_user_msg(context: Context) -> Artifact[UserMsg] | None:
    messages = context.list_artifacts(UserMsg)
    return max((m for m in messages), key=lambda m: m.created_at, default=None)


def _project_artifact(context: Context) -> Artifact[Project] | None:
    projects = context.list_artifacts(Project)
    return projects[0] if projects else None


def _update_project(project_art: Artifact[Project], updates: dict[str, Any]) -> Patch:
    return Patch().update_fields(project_art, **updates)


def _reply(
    context: Context,
    msg_id: str,
    text: str,
    kind: str = "text",
    images: list[str] | None = None,
) -> Patch:
    return Patch().create(
        ChatReply(query_id=msg_id, text=text, kind=kind, images=images or []),
        id=f"reply:{msg_id}",
    )


async def _extract_info(
    context: Context, text: str, current: ProjectInfo
) -> ProjectInfo:
    context.announce("Анализирую детали проекта…", kind="status")
    result = await structured_llm(
        context,
        schema=ProjectInfo,
        user=(
            "Извлеки факты о ремонте. Не домысливай: неизвестные поля = null.\n"
            f"Сообщение: {text}"
        ),
    )
    if result is None:
        return current
    updates = {k: v for k, v in result.model_dump().items() if v is not None}
    return current.model_copy(update=updates)


async def _make_design_options(
    context: Context, info: ProjectInfo
) -> list[DesignOption] | None:
    """Designs from the LLM. If a model is configured but returns no valid options —
    return None (an honest failure), not canned stubs. The deterministic
    fallback remains for demo mode without an LLM only."""
    context.announce("Подбираю варианты дизайна…", kind="status")
    prefs = _list_preferences(info)
    prefs_text = f"Пожелания пользователя: {prefs}. " if prefs else ""
    result = await structured_llm(
        context,
        schema=DesignOptions,
        user=(
            "Предложи 3 варианта дизайна комнаты, учитывая пожелания пользователя "
            "(стиль можно варьировать, но заявленные пожелания соблюдай). "
            "Каждый вариант: name, palette (style, wall_color, ceiling_color, "
            "floor_material — словами на русском), description.\n"
            f"{prefs_text}Геометрия: {geometry_text(info)}"
        ),
    )
    if result is not None and result.options:
        options = result.options
    elif context.resources.llm is None:
        options = fallback_options(info)
    else:
        return None  # the model gave no options — do not substitute stubs

    images = context.resources.get("images")
    if images is not None:
        context.announce("Рендерю фото-превью вариантов…", kind="status")
        options = await _render_previews(context, images, info, options)
    return options


def _list_preferences(info: ProjectInfo) -> str:
    """User preferences pulled from the facts (version/palette) for the design constructor."""
    items = [
        ("стиль", info.style),
        ("цвет стен", info.wall_color),
        ("цвет потолка", info.ceiling_color),
        ("пол", info.floor_material),
    ]
    return ", ".join(f"{label}: {value}" for label, value in items if value)


async def _render_previews(
    context: Context,
    images: Any,
    info: ProjectInfo,
    options: list[DesignOption],
) -> list[DesignOption]:
    """Sequential preview rendering with a timeout and retries.

    OpenRouter /images answers 429 on parallel requests — render strictly one
    by one, pausing between retries to stay within the rate limit. Each call is
    bounded by `asyncio.wait_for`; a single option failing does not break the flow (§59).
    """
    raw_dir = context.resources.get("images_dir")
    if not raw_dir:
        return options
    from pathlib import Path

    out_dir = Path(raw_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    total = len(options)
    timeout: float = context.resources.get("images_timeout") or _IMAGE_RENDER_TIMEOUT
    retries: int = int(context.resources.get("images_retries") or _IMAGE_RENDER_RETRIES)
    retry_delay: float = float(
        context.resources.get("images_retry_delay") or _IMAGE_RETRY_DELAY
    )
    rendered: list[DesignOption] = []
    for index, option in enumerate(options):
        png = None
        for attempt in range(retries):
            try:
                png = await asyncio.wait_for(
                    images.generate(
                        build_image_prompt(info, option),
                        aspect_ratio="1:1",
                        output_format="png",
                    ),
                    timeout=timeout,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "preview %s attempt %s failed: %r", index + 1, attempt + 1, exc
                )
                png = None
            if png:
                break
            if attempt + 1 < retries:
                await asyncio.sleep(retry_delay)  # pause against 429
        context.announce(
            f"Превью {index + 1}/{total} готово"
            if png
            else f"Превью {index + 1}/{total}: пропущено",
            kind="status",
        )
        if png:
            name = f"design-{index}-{uuid.uuid4().hex[:8]}.png"
            (out_dir / name).write_bytes(png)
            rendered.append(
                option.model_copy(update={"preview": f"/assets/generated/{name}"})
            )
        else:
            rendered.append(option)
    return rendered


_IMAGE_RENDER_TIMEOUT = 60.0
_IMAGE_RENDER_RETRIES = 3
_IMAGE_RETRY_DELAY = 2.0


async def _make_plan(context: Context, project: Project) -> list[PlanStep]:
    info = project.info
    palette = _palette_text(project)
    budget = f"{info.budget:,.0f} ₽".replace(",", " ") if info.budget else "не задан"
    geometry = (
        f"площадь пола {info.floor_area} м², стен {info.walls_area} м², "
        f"потолка {info.ceiling_area} м², периметр {info.perimeter} м, "
        f"высота потолков {info.ceiling_height} м"
    )
    context.announce("Составляю план ремонта…", kind="status")
    result = await structured_llm(
        context,
        schema=RepairPlan,
        user=_PLAN_PROMPT.format(geometry=geometry, palette=palette, budget=budget),
    )
    if result is None or not result.steps:
        return fallback_plan(info)
    return result.steps


_PLAN_PROMPT = """Ты — Planner. Составь поэтапный план ремонта помещения.

Геометрия уже вычислена: {geometry}
Бюджет: {budget}
Выбранный дизайн: {palette}

ПОРЯДОК ЭТАПОВ — строго такой (пропускай ненужные, но не меняй порядок):
1. Демонтаж и подготовка
2. Черновые работы (стяжка, выравнивание, штукатурка, шпаклёвка)
3. Электромонтаж и разводка
4. Сантехнические работы (если нужны)
5. Отделка стен (покраска или обои)
6. Отделка потолка
7. Укладка пола (подложка, ламинат/плитка/линолеум, плинтус)
8. Финишная отделка и декор

Правила:
- название этапа короткое; описание НЕ повторяет название и добавляет новое;
- УКЛАДЫВАЙСЯ В БЮДЖЕТ {budget}: выбирай доступные материалы и адекватные
  количества, чтобы итоговая смета не выходила за бюджет;
- ПРИВЯЗКА МАТЕРИАЛОВ: штукатурка/шпаклёвка/грунтовка/стяжка/цемент — только в
  «Черновые работы»; кабель/розетки — «Электромонтаж»; плитка/клей — в укладку
  плитки; краска/обои — стены/потолок; ламинат/подложка/плинтус — пол;
- на каждый этап перечислите материалы с количеством через «~» (например,
  «штукатурка ~30 мешков», «подложка ~10 м²»), чтобы потом была точная смета.
  Цены не указывай;
- учитывай выбранный дизайн (стиль, цвета, покрытие пола).

Верни ТОЛЬКО JSON без пояснений:
{{"steps": [{{"name": "", "description": "", "materials": ["..."]}}]}}"""


def _palette_text(project: Project) -> str:
    parts = []
    if project.design_choice:
        parts.append(f"вариант: {project.design_choice}")
    if project.palette:
        parts.append(", ".join(f"{k}: {v}" for k, v in project.palette.items() if v))
    if project.info.style:
        parts.append(f"стиль: {project.info.style}")
    return "; ".join(parts) if parts else "свободный выбор"


def _parse_pick(text: str, options: list[DesignOption]) -> DesignOption | None:
    match = _PICK_NUMBER.match(text.strip())
    if match and 1 <= int(match.group(1)) <= len(options):
        return options[int(match.group(1)) - 1]
    targets = stem_words(text)
    for option in options:
        if stem_words(option.name) & targets:
            return option
    return None


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


def _downstream_resets(target: str) -> dict[str, Any]:
    """What to reset when rolling back to `target` (the change model from services)."""
    resets: dict[str, Any] = {}
    if target in ("collect", "design_choice"):
        resets["design_options"] = []
    if target in ("collect", "design_choice"):
        resets["design_choice"] = ""
    if target in ("collect", "design_choice"):
        resets["palette"] = {}
    if target in ("collect", "design_choice", "plan"):
        resets["plan"] = []
    if target in ("collect", "design_choice", "plan", "estimate"):
        resets["estimate"] = None
    return resets


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


def _assistant_context(project: Project) -> str:
    """A brief project summary for the post-approval assistant."""
    parts = [
        f"Комната: {project.info.room_type}, {project.info.area} м²"
        if project.info.area
        else f"Комната: {project.info.room_type}",
        f"бюджет {project.info.budget} ₽" if project.info.budget else "",
        f"вариант: {project.design_choice}" if project.design_choice else "",
    ]
    head = "; ".join(p for p in parts if p)
    lines = "\n".join(f"- {s.name}: {s.description}" for s in project.plan)
    total = project.estimate.total if project.estimate is not None else None
    tail = f"Итог: {total} ₽." if total else ""
    return f"{head}.\nПлан:\n{lines}\n{tail}"


def _conversation_text(context: Context, current_msg_id: str, limit: int = 10) -> str:
    """Conversation history up to the current message — chat memory (§27).

    Retrieved via `context.view`: type (UserMsg|ChatReply), excluding the current
    message, the last `limit` records. Formatting — tailored to the prompt.
    """
    view = context.view(
        (UserMsg, ChatReply),
        condition=lambda a: a.id != current_msg_id,
    )
    ordered = sorted(view.artifacts, key=lambda a: a.created_at)
    recent = ordered[-limit:]
    if not recent:
        return ""
    lines = [
        f"user: {a.data.text}"
        if isinstance(a.data, UserMsg)
        else f"assistant: {a.data.text}"
        for a in recent
    ]
    return "Разговор:\n" + "\n".join(lines)


def _approval_text(project: Project) -> str:
    info = project.info
    steps = "\n".join(f"- {s.name}: {s.description}" for s in project.plan)
    est_lines = project.estimate.lines if project.estimate is not None else []
    lines = "\n".join(
        f"- {line.name}: {line.quantity} {line.unit} × {line.unit_price} ₽ = {line.total} ₽"
        for line in est_lines
    )
    total = project.estimate.total if project.estimate is not None else 0
    return (
        f"Комната: {info.room_type}, {info.area} м², бюджет {info.budget} ₽.\n"
        f"План:\n{steps}\nСмета:\n{lines}\nИтого: {total} ₽\n\nУтвердить (да) или изменить?"
    )
