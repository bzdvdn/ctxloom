from ctxloom.providers import LLMProvider, LLMRequest, LLMResponse
from examples.repair.web import create_app
from fastapi.testclient import TestClient


class EmptyLLM(LLMProvider):
    """An honestly empty LLM: extracts nothing (independent of .env/network)."""

    async def complete(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(text="{}")

    async def stream(self, request):
        yield LLMResponse(text="")


class BoomLLM(LLMProvider):
    """A provider that fails: network/5xx."""

    async def complete(self, request: LLMRequest) -> LLMResponse:
        raise RuntimeError("upstream down")

    async def stream(self, request):
        yield LLMResponse(text="")


def test_sse_stream_greeting(tmp_path):
    app = create_app(llm=EmptyLLM(), store_dir=str(tmp_path))
    client = TestClient(app)

    with client.stream(
        "POST",
        "/api/chat/stream",
        json={"message": "привет", "session_id": "s1"},
    ) as response:
        body = "".join(response.iter_text())

    assert "event: session" in body
    assert "event: message" in body
    assert "Здравствуйте" in body


def test_sse_missing_facts_asks(tmp_path):
    app = create_app(llm=EmptyLLM(), store_dir=str(tmp_path))
    client = TestClient(app)

    with client.stream(
        "POST",
        "/api/chat/stream",
        json={"message": "просто ремонт", "session_id": "s2"},
    ) as response:
        body = "".join(response.iter_text())

    assert "Уточните" in body


def test_runs_routes(tmp_path):
    app = create_app(llm=EmptyLLM(), store_dir=str(tmp_path))
    client = TestClient(app)

    r = client.get("/api/health")
    assert r.json() == {"ok": True}

    with client.stream(
        "POST",
        "/api/chat/stream",
        json={"message": "привет", "session_id": "s3"},
    ):
        pass

    runs = client.get("/api/runs/s3").json()
    assert any(m["role"] == "user" for m in runs["messages"])
    assert any(m["role"] == "assistant" for m in runs["messages"])

    assert client.delete("/api/runs/s3").json() == {"ok": True}
    assert client.get("/api/runs/s3").json()["messages"] == []


def test_capabilities_over_sse(tmp_path):
    app = create_app(llm=BoomLLM(), store_dir=str(tmp_path))
    client = TestClient(app)

    with client.stream(
        "POST",
        "/api/chat/stream",
        json={"message": "что ты умеешь?", "session_id": "s4"},
    ) as response:
        body = "".join(response.iter_text())

    assert "Что я умею" in body
    assert "event: status" in body  # a live «Думаю…» status before the reply
    assert "Думаю" in body


def test_llm_failure_not_empty_reply(tmp_path):
    app = create_app(llm=BoomLLM(), store_dir=str(tmp_path))
    client = TestClient(app)

    with client.stream(
        "POST",
        "/api/chat/stream",
        json={"message": "сделай ремонт ванной", "session_id": "s5"},
    ) as response:
        body = "".join(response.iter_text())

    # not an empty reply and not a broken stream: an honest fallback (§59)
    assert "event: message" in body
    assert '"reply": ""' not in body
