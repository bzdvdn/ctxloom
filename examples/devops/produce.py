"""Devops demo logic: base chat router, report builders, render.

Agents are thin containers (agents.py); produce live here:
- `RouteProblem` — question → problem artifact for the relevant LLM agent. Which
  agent the question addresses is decided by the LLM itself (routing is reasoning,
  §68); the keyword fallback is a deterministic path without an LLM (§67);
- `_ReportBuilder` — ToolAnswer(agent) → domain report (each agent
  processes the result its own way);
- `RenderReply` — report → ChatReply for the chat.
"""

from __future__ import annotations

from typing import Any, Literal

from ctxloom import ToolAnswer, structured_llm
from ctxloom.artifacts import Artifact
from ctxloom.context import Context
from ctxloom.events import Event
from ctxloom.patches import Patch
from ctxloom.produce import Produce
from pydantic import BaseModel

from .models import (
    AnsibleProblem,
    AnsibleReport,
    ChatReply,
    GitlabProblem,
    GitlabReport,
    K8sProblem,
    K8sReport,
    UserMsg,
)
from .prompts import ROUTE_SYSTEM

# keyword fallback for when the LLM is unavailable or undecided
_K8S_HINTS = (
    "k8s",
    "kubernetes",
    "кластер",
    "под",
    "поды",
    "pod",
    "pods",
    "деплоймент",
    "deployment",
    "crash",
    "replica",
    "cluster",
    "node",
    "container",
)
_GITLAB_HINTS = (
    "gitlab",
    "mr",
    "merge request",
    "ci",
    "pipeline",
    "пайплайн",
    "коммит",
    "commit",
)
_ANSIBLE_HINTS = ("ansible", "playbook", "плейбук", "inventory")

HELP_TEXT = (
    "I help with k8s, GitLab, and Ansible. For example:\n"
    "• «why is a pod in the cluster crashing?»\n"
    "• «what is the status of the GitLab pipeline?»\n"
    "• «what does the playbook say about the deploy?»"
)


class RouteDecision(BaseModel):
    """Router decision: which system the question belongs to."""

    target: Literal["k8s", "gitlab", "ansible", "none"] = "none"


def _keyword_target(text: str) -> str:
    low = text.lower()
    if any(hint in low for hint in _K8S_HINTS):
        return "k8s"
    if any(hint in low for hint in _GITLAB_HINTS):
        return "gitlab"
    if any(hint in low for hint in _ANSIBLE_HINTS):
        return "ansible"
    return "none"


class RouteProblem(Produce[K8sProblem]):
    """Base chat: question → problem artifact of the relevant LLM agent (§48).

    The LLM makes the routing decision (routing is reasoning, §68); if the LLM
    is unavailable or did not answer — the keyword fallback (§67).
    """

    artifact_type = K8sProblem

    async def produce(
        self,
        context: Context,
        inputs: list[Artifact[Any]],
        event: Event | None = None,
    ) -> Patch | None:
        msg = context.get(event.artifact_id) if event is not None else None
        if msg is None or not isinstance(msg.data, UserMsg):
            return None
        context.announce("Parsing the question…", kind="status")
        target = await self._route(context, msg.data.text)
        patch = Patch()
        if target == "k8s":
            patch.create(K8sProblem(text=msg.data.text, query_id=msg.id))
        elif target == "gitlab":
            patch.create(GitlabProblem(text=msg.data.text, query_id=msg.id))
        elif target == "ansible":
            patch.create(AnsibleProblem(text=msg.data.text, query_id=msg.id))
        else:
            patch.create(
                ChatReply(query_id=msg.id, text=HELP_TEXT),
                id=f"reply:{msg.id}",
            )
        return patch

    @staticmethod
    async def _route(context: Context, text: str) -> str:
        decision = await structured_llm(
            context,
            schema=RouteDecision,
            system=ROUTE_SYSTEM,
            user=text,
        )
        if decision is not None and decision.target in ("k8s", "gitlab", "ansible"):
            return decision.target
        return _keyword_target(text)


class _ReportBuilder(Produce[BaseModel]):
    """Common report builder: ToolAnswer → domain report.

    The agent has already been filtered by the `Consume.by_field(ToolAnswer, "agent", …)`
    consume, so checking the type here is enough. ToolAnswer.query_id points to the
    problem artifact; its `query_id` holds the id of the original message.
    """

    report_type: type[BaseModel] = BaseModel

    async def produce(
        self,
        context: Context,
        inputs: list[Artifact[Any]],
        event: Event | None = None,
    ) -> Patch | None:
        a = context.get(event.artifact_id) if event is not None else None
        if a is None or not isinstance(a.data, ToolAnswer):
            return None
        problem = context.get(a.data.query_id)
        qid = getattr(problem.data, "query_id", "") if problem else ""
        return Patch().create(self.report_type(query_id=qid, text=a.data.text))


class K8sReportBuilder(_ReportBuilder):
    artifact_type = K8sReport
    report_type = K8sReport


class GitlabReportBuilder(_ReportBuilder):
    artifact_type = GitlabReport
    report_type = GitlabReport


class AnsibleReportBuilder(_ReportBuilder):
    artifact_type = AnsibleReport
    report_type = AnsibleReport


class RenderReply(Produce[ChatReply]):
    """Agent report → chat reply (stable id reply:<query_id>)."""

    artifact_type = ChatReply

    async def produce(
        self,
        context: Context,
        inputs: list[Artifact[Any]],
        event: Event | None = None,
    ) -> Patch | None:
        a = context.get(event.artifact_id) if event is not None else None
        if a is None or not isinstance(
            a.data, (K8sReport, GitlabReport, AnsibleReport)
        ):
            return None
        return Patch().create(
            ChatReply(query_id=a.data.query_id, text=a.data.text),
            id=f"reply:{a.data.query_id}",
        )
