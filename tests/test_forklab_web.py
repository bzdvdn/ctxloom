"""forklab web: the fork → merge pipeline streams status events and a result."""

from ctxloom.providers import LLMProvider, LLMRequest, LLMResponse
from examples.forklab.web import create_app
from fastapi.testclient import TestClient


class ScriptedLLM(LLMProvider):
    def __init__(self, responses):
        self.responses = list(responses)

    async def complete(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(text=self.responses.pop(0))

    async def stream(self, request):
        yield LLMResponse()  # pragma: no cover


def _word(raw: str) -> str:
    return '{"text": "' + raw + '"}'


def _events(body: str) -> dict[str, list]:
    out: dict[str, list] = {}
    event = "message"
    data: list[str] = []
    for line in body.splitlines():
        if line.startswith("event:"):
            event = line.split(":", 1)[1].strip()
        elif line.startswith("data:"):
            data.append(line.split(":", 1)[1].strip())
        elif line.strip() == "":
            out.setdefault(event, []).append("\n".join(data))
            event = "message"
            data = []
    if data:
        out.setdefault(event, []).append("\n".join(data))
    return out


def test_ask_stream_returns_result_with_provenance():
    llm = ScriptedLLM(
        [
            _word("web depth"),
            _word("web breadth 1"),
            _word("web breadth 2"),
            _word("web breadth 3"),
            _word("web answer"),
        ]
    )
    app = create_app(llm=llm)
    client = TestClient(app)
    res = client.post(
        "/api/ask/stream",
        json={"message": "Which design recovers the most thermal energy?"},
    )
    assert res.status_code == 200
    events = _events(res.text)

    statuses = [
        __import__("json").loads(d)["message"] for d in events.get("status", [])
    ]
    assert any("merging" in s for s in statuses)
    assert any("depth" in s for s in statuses)
    assert any("breadth" in s for s in statuses)

    results = events.get("result", [])
    assert len(results) == 1
    result = __import__("json").loads(results[0])
    assert result["answer"] == "web answer"
    assert result["sources"][0] == "doc:overview"
    assert result["splits"] == {"depth": 1, "breadth": 3}
    assert "supported_by" in result["mermaid"]
    assert llm.responses == []  # all five model calls were consumed
