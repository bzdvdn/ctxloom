"""medic-lab web: SSE flow — question → steering → answer → report (fixtures)."""

import json

from examples.medic_lab.main import create_app
from fastapi.testclient import TestClient


def _frames(body: str) -> list[tuple[str, dict]]:
    frames = []
    for part in body.split("\n\n"):
        event, data = None, None
        for line in part.split("\n"):
            if line.startswith("event:"):
                event = line[6:].strip()
            elif line.startswith("data:"):
                data = line[5:].strip()
        if data:
            frames.append((event, json.loads(data)))
    return frames


def test_stream_asks_steering_then_answer_reports(tmp_path):
    app = create_app(llm=None, store_dir=str(tmp_path))  # llm=None → hermetic
    client = TestClient(app)

    with client.stream(
        "POST",
        "/api/chat/stream",
        json={
            "message": "does vitamin D supplementation prevent colds?",
            "session_id": "s1",
        },
    ) as response:
        body = "".join(response.iter_text())

    events = _frames(body)
    assert any(e == "status" for e, _ in events)
    message_events = [d for e, d in events if e == "message"]
    assert message_events, "expected a terminal message"
    assert message_events[-1]["waiting"] is True  # steering question first
    assert message_events[-1]["steer"] is True

    with client.stream(
        "POST",
        "/api/chat/answer",
        json={"session_id": "s1", "reply": "stop"},
    ) as response:
        body2 = "".join(response.iter_text())

    events2 = _frames(body2)
    finals = [d for e, d in events2 if e == "message" and d.get("waiting") is False]
    assert finals, "expected the final report"
    assert "Most supported" in finals[-1]["reply"]
