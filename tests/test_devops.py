import asyncio

from ctxloom import (
    Budget,
    Context,
    PendingQuestion,
    Runtime,
    RuntimeResources,
)
from ctxloom.providers import LLMProvider, LLMRequest, LLMResponse
from examples.devops.agents import (
    AnsibleAgent,
    GitlabAgent,
    K8sAgent,
    RenderAgent,
    RouteAgent,
)
from examples.devops.models import ChatReply, GitlabReport, K8sReport, UserMsg
from examples.devops.tools import CALLS


class ScriptedLLM(LLMProvider):
    """The LLM "decides" which tool to call and when to answer."""

    def __init__(self, responses):
        self.responses = list(responses)

    async def complete(self, request: LLMRequest) -> LLMResponse:
        text = self.responses.pop(0) if self.responses else "{}"
        return LLMResponse(text=text)

    async def stream(self, request):
        yield LLMResponse(text="")


def build_runtime(llm):
    resources = RuntimeResources(llm=llm)
    ctx = Context(resources=resources)
    runtime = Runtime(
        ctx,
        agents=[
            RouteAgent(),
            K8sAgent(),
            GitlabAgent(),
            AnsibleAgent(),
            RenderAgent(),
        ],
        budget=Budget(max_runs=200, max_tool_calls=12),
    )
    return ctx, runtime


def replies_for(ctx, query_id):
    return [r for r in ctx.list_artifacts(ChatReply) if r.data.query_id == query_id]


def test_k8s_flow_uses_tool_and_replies():
    CALLS.clear()
    llm = ScriptedLLM(
        [
            '{"target":"k8s"}',
            '{"type":"tool_call","tool":"kubectl_get","args":{"resource":"pods","namespace":"default"}}',
            '{"type":"answer","text":"Под worker-2f1 в CrashLoopBackOff — смотрим логи."}',
        ]
    )
    ctx, runtime = build_runtime(llm)
    msg = ctx.create(UserMsg(text="почему падает под в кластере?"))
    asyncio.run(runtime.arun())

    replies = replies_for(ctx, msg.id)
    assert len(replies) == 1
    assert "CrashLoopBackOff" in replies[0].data.text
    assert CALLS["kubectl_get"] == 1
    # other agents were not woken up
    assert ctx.list_artifacts(K8sReport)
    assert ctx.list_artifacts(GitlabReport) == []


def test_gitlab_flow_replies():
    CALLS.clear()
    llm = ScriptedLLM(
        [
            '{"target":"gitlab"}',
            '{"type":"tool_call","tool":"gitlab_pipeline","args":{"project":"payments"}}',
            '{"type":"answer","text":"Пайплайн #4821 упал на deploy."}',
        ]
    )
    ctx, runtime = build_runtime(llm)
    msg = ctx.create(UserMsg(text="статус пайплайна в gitlab?"))

    async def run():
        async for _ in runtime.astream():
            pass

    asyncio.run(run())

    replies = replies_for(ctx, msg.id)
    assert len(replies) == 1
    assert "deploy" in replies[0].data.text
    assert CALLS["gitlab_pipeline"] == 1


def test_help_when_no_match():
    llm = ScriptedLLM(['{"target":"none"}'])
    ctx, runtime = build_runtime(llm)
    msg = ctx.create(UserMsg(text="привет"))
    asyncio.run(runtime.arun())
    replies = replies_for(ctx, msg.id)
    assert len(replies) == 1
    assert "k8s" in replies[0].data.text
    assert "GitLab" in replies[0].data.text


def test_two_agents_in_one_session_no_crossfire():
    CALLS.clear()
    llm = ScriptedLLM(
        [
            '{"target":"k8s"}',
            '{"type":"tool_call","tool":"kubectl_get","args":{"resource":"pods","namespace":"default"}}',
            '{"type":"answer","text":"k8s: ок"}',
            '{"target":"gitlab"}',
            '{"type":"tool_call","tool":"gitlab_pipeline","args":{"project":"api"}}',
            '{"type":"answer","text":"gitlab: пайплайн упал"}',
        ]
    )
    ctx, runtime = build_runtime(llm)

    m1 = ctx.create(UserMsg(text="почему падает pod в кластере?"))
    asyncio.run(runtime.arun())
    m2 = ctx.create(UserMsg(text="статус пайплайна gitlab?"))
    asyncio.run(runtime.arun())

    r1 = replies_for(ctx, m1.id)
    r2 = replies_for(ctx, m2.id)
    assert len(r1) == 1 and "k8s: ок" in r1[0].data.text
    assert len(r2) == 1 and "gitlab: пайплайн упал" in r2[0].data.text
    assert CALLS["kubectl_get"] == 1
    assert CALLS["gitlab_pipeline"] == 1


def test_k8s_agent_asks_namespace_and_continues():
    """HITL: the k8s agent asks for namespace, the human answers, the loop continues."""
    CALLS.clear()
    llm = ScriptedLLM(
        [
            '{"target":"k8s"}',
            '{"type":"ask","text":"В каком namespace разворачивается clickhouse?"}',
            '{"type":"tool_call","tool":"kubectl_get","args":{"resource":"deployments","namespace":"production"}}',
            '{"type":"answer","text":"В production деплой clickhouse в CrashLoopBackOff."}',
        ]
    )
    ctx, runtime = build_runtime(llm)
    msg = ctx.create(UserMsg(text="у меня не раскатывается clickhouse"))
    asyncio.run(runtime.arun())

    questions = ctx.list_artifacts(PendingQuestion)
    assert len(questions) == 1
    assert questions[0].data.kind == "clarify"
    assert "namespace" in questions[0].data.question
    assert "kubectl_get" not in CALLS  # tool was not called before the clarification

    ctx.resume(questions[0].id, "production")
    asyncio.run(runtime.arun())

    replies = replies_for(ctx, msg.id)
    assert len(replies) == 1
    assert "CrashLoopBackOff" in replies[0].data.text
    assert CALLS["kubectl_get"] == 1
