"""devops reply — an agent's domain report becomes the chat reply."""

from __future__ import annotations

from typing import Any

from ctxloom import Artifact, Context, Event, Patch, Produce

from ..models import AnsibleReport, ChatReply, GitlabReport, K8sReport


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
