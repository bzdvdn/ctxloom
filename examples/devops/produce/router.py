"""devops router — a question becomes the right LLM agent's problem artifact."""

from __future__ import annotations

from typing import Any

from ctxloom import Artifact, Context, Event, Produce

from ..models import (
    AnsibleProblem,
    ChatReply,
    GitlabProblem,
    K8sProblem,
    UserMsg,
)
from .common import HELP_TEXT, route_target


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
    ) -> None:
        msg = context.get(event.artifact_id) if event is not None else None
        if msg is None or not isinstance(msg.data, UserMsg):
            return None
        context.announce("Parsing the question…", kind="status")
        target = await route_target(context, msg.data.text)
        if target == "k8s":
            self.effects.create(K8sProblem(text=msg.data.text, query_id=msg.id))
        elif target == "gitlab":
            self.effects.create(GitlabProblem(text=msg.data.text, query_id=msg.id))
        elif target == "ansible":
            self.effects.create(AnsibleProblem(text=msg.data.text, query_id=msg.id))
        else:
            self.effects.create(
                ChatReply(query_id=msg.id, text=HELP_TEXT),
                id=f"reply:{msg.id}",
            )
        return None
