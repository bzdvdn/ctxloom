"""Video providers: submit → poll → download contract (Sora + Runway)."""

import asyncio

import httpx
from ctxloom.providers import (
    RunwayVideoProvider,
    SoraVideoProvider,
    VideoResult,
    video_from_env,
)


def sora_transport(states: dict) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(200, json={"id": "video_1", "status": "queued"})
        task_id = request.url.path.rsplit("/", 1)[-1]
        state = states.get(task_id, states.get("default", ""))
        if state == "done":
            return httpx.Response(
                200,
                json={
                    "id": task_id,
                    "status": "completed",
                    "output": {"url": "https://cdn.example/v.mp4"},
                },
            )
        if state == "failed":
            return httpx.Response(
                200,
                json={"id": task_id, "status": "failed", "output": {"error": "boom"}},
            )
        return httpx.Response(200, json={"id": task_id, "status": "in_progress"})

    return httpx.MockTransport(handler)


def test_sora_generate_and_poll():
    states = {"video_1": "done"}
    provider = SoraVideoProvider(api_key="sk", transport=sora_transport(states))
    task_id = asyncio.run(provider.generate("a cat in space", size="1920x1080"))
    assert task_id == "video_1"
    result = asyncio.run(provider.poll(task_id, timeout=10, interval=0.001))
    assert result.status == "completed"
    assert result.url == "https://cdn.example/v.mp4"


def test_sora_failed_state():
    provider = SoraVideoProvider(
        api_key="sk", transport=sora_transport({"video_2": "failed"})
    )
    result = asyncio.run(provider.poll("video_2", timeout=10, interval=0.001))
    assert result.status == "failed"
    assert result.error == "boom"


def test_runway_maps_statuses():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(200, json={"id": "rw_1"})
        return httpx.Response(200, json={"status": "SUCCEEDED"})

    provider = RunwayVideoProvider(api_key="rw", transport=httpx.MockTransport(handler))
    task_id = asyncio.run(provider.generate("busy city"))
    assert task_id == "rw_1"
    result = asyncio.run(provider.poll(task_id, timeout=3, interval=0))
    assert result.status == "completed"


def test_download_bytes():
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url).endswith(".mp4"):
            return httpx.Response(200, content=b"\x00fakevideo")
        return httpx.Response(
            200,
            json={
                "id": "v",
                "status": "completed",
                "output": {"url": "https://cdn.example/v.mp4"},
            },
        )

    provider = SoraVideoProvider(api_key="sk", transport=httpx.MockTransport(handler))
    result = asyncio.run(provider.fetch("v"))
    blob = asyncio.run(provider.download(result))
    assert blob == b"\x00fakevideo"


def test_poll_embedded_bytes_no_network():
    result = VideoResult(id="x", status="completed", data=b"\x00lenny")
    provider = SoraVideoProvider(
        api_key="sk"
    )  # no transport: download must not hit network
    blob = asyncio.run(provider.download(result))
    assert blob == b"\x00lenny"


def test_video_from_env_runway():
    import os

    saved = {
        k: os.environ.get(k)
        for k in ("VIDEO_PROVIDER", "RUNWAY_API_KEY", "VIDEO_PROXY", "VIDEO_API_KEY")
    }
    try:
        os.environ["VIDEO_PROVIDER"] = "runway"
        os.environ["RUNWAY_API_KEY"] = "rw-env"
        os.environ["VIDEO_PROXY"] = "http://proxy.example:8080"
        os.environ.pop("VIDEO_API_KEY", None)
        provider = video_from_env()
    finally:
        for k in saved:
            if saved[k] is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = saved[k]
    assert isinstance(provider, RunwayVideoProvider)
    assert provider._proxy == "http://proxy.example:8080"


def luma_transport() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(200, json={"id": "luma_1", "state": "queued"})
        return httpx.Response(
            200,
            json={
                "id": "luma_1",
                "state": "completed",
                "assets": {"video": "https://cdn.luma/v.mp4"},
            },
        )

    return httpx.MockTransport(handler)


def test_luma_generate_poll_and_download():
    from ctxloom.providers import LumaVideoProvider

    provider = LumaVideoProvider(api_key="luma", transport=luma_transport())
    task_id = asyncio.run(provider.generate("waves"))
    assert task_id == "luma_1"
    result = asyncio.run(provider.poll(task_id, timeout=5, interval=0))
    assert result.status == "completed"
    assert result.url == "https://cdn.luma/v.mp4"


def test_video_from_env_luma():
    import os

    saved = {
        k: os.environ.get(k)
        for k in ("VIDEO_PROVIDER", "LUMA_API_KEY", "VIDEO_API_KEY")
    }
    try:
        os.environ["VIDEO_PROVIDER"] = "luma"
        os.environ["LUMA_API_KEY"] = "luma-env"
        os.environ.pop("VIDEO_API_KEY", None)
        provider = video_from_env()
    finally:
        for k in saved:
            if saved[k] is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = saved[k]
    from ctxloom.providers import LumaVideoProvider

    assert isinstance(provider, LumaVideoProvider)
    assert provider.api_key == "luma-env"


def openrouter_video_transport() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(200, json={"id": "gen_1", "out": [], "link": "/x"})
        return httpx.Response(
            200,
            json={
                "id": "gen_1",
                "out": [{"video_url": "https://cdn.or/v.mp4", "qid": 0}],
            },
        )

    return httpx.MockTransport(handler)


def test_openrouter_video_generate_and_fetch():
    from ctxloom.providers import OpenRouterVideoProvider

    provider = OpenRouterVideoProvider(
        api_key="or", transport=openrouter_video_transport()
    )
    task_id = asyncio.run(provider.generate("drone over city"))
    assert task_id == "gen_1"
    result = asyncio.run(provider.fetch(task_id))
    assert result.status == "completed"
    assert result.url == "https://cdn.or/v.mp4"


def test_video_from_env_openrouter():
    import os

    saved = {
        k: os.environ.get(k)
        for k in ("VIDEO_PROVIDER", "OPENROUTER_API_KEY", "VIDEO_API_KEY")
    }
    try:
        os.environ["VIDEO_PROVIDER"] = "openrouter"
        os.environ["OPENROUTER_API_KEY"] = "or-env"
        os.environ.pop("VIDEO_API_KEY", None)
        provider = video_from_env()
    finally:
        for k in saved:
            if saved[k] is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = saved[k]
    from ctxloom.providers import OpenRouterVideoProvider

    assert isinstance(provider, OpenRouterVideoProvider)
    assert provider.api_key == "or-env"
