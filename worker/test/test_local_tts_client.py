"""Local-TTS 클라이언트 사본 단위 테스트 (httpx.MockTransport, 서버 불필요)."""
import json

import httpx
import pytest

from ai_worker.tts.local_tts_client import (
    ConnectionFailed,
    InvalidRequest,
    JobFailed,
    LocalTTS,
    RateLimited,
    Unavailable,
)

pytestmark = pytest.mark.unit


def _client(handler, **kw) -> LocalTTS:
    kw.setdefault("max_retries", 2)
    return LocalTTS("http://tts.test", client="wagglebot", transport=httpx.MockTransport(handler),
                    sleep=lambda s: None, **kw)


def test_create_job_body_and_headers() -> None:
    seen = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return httpx.Response(202, json={"id": "j1", "state": "queued"})

    job = _client(handler).create_job(
        "안녕", {"voice": "M1", "normalize": {"profile": "wagglebot/shorts-ko"}, "speed": None},
        request_id="wb-1-intro-ab", idempotency="k1",
    )
    assert job["id"] == "j1"
    req = seen[0]
    body = json.loads(req.content)
    assert req.url.path == "/v1/jobs"
    assert body["input"] == "안녕"
    assert "request_id" not in body                       # 최상위 금지(extra=forbid)
    assert body["options"]["request_id"] == "wb-1-intro-ab"  # options 안
    assert body["options"]["voice"] == "M1"
    assert "speed" not in body["options"]                 # None 은 전송하지 않음
    assert req.headers["x-client-id"] == "wagglebot"
    assert req.headers["idempotency-key"] == "k1"
    assert req.headers["x-request-id"] == "wb-1-intro-ab"


def test_429_retries_with_retry_after_then_succeeds() -> None:
    calls = []
    sleeps: list[float] = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(1)
        if len(calls) < 3:
            return httpx.Response(429, headers={"retry-after": "7"},
                                  json={"error": {"code": "queue_full", "message": "full"}})
        return httpx.Response(202, json={"id": "j2"})

    c = LocalTTS("http://tts.test", transport=httpx.MockTransport(handler), sleep=sleeps.append, max_retries=3)
    assert c.create_job("x")["id"] == "j2"
    assert len(calls) == 3 and sleeps == [7.0, 7.0]


def test_503_exhausted_raises_unavailable_and_429_ratelimited() -> None:
    c = _client(lambda r: httpx.Response(503, json={"error": {"code": "model_loading"}}), max_retries=1)
    with pytest.raises(Unavailable):
        c.create_job("x")
    c = _client(lambda r: httpx.Response(429, json={"error": {"code": "queue_full"}}), max_retries=1)
    with pytest.raises(RateLimited):
        c.create_job("x")


def test_connection_error_retried_only_with_idempotency_key() -> None:
    n = {"c": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        n["c"] += 1
        raise httpx.ConnectError("refused")

    with pytest.raises(ConnectionFailed):
        _client(handler).create_job("x")                    # 키 없음 -> 재시도 없음
    assert n["c"] == 1
    n["c"] = 0
    with pytest.raises(ConnectionFailed):
        _client(handler).create_job("x", idempotency=True)  # 키 있음 -> 재시도
    assert n["c"] == 3


def test_422_empty_input_maps_to_invalid_request() -> None:
    c = _client(lambda r: httpx.Response(400, json={"error": {"code": "empty_input", "message": "empty"}}))
    with pytest.raises(InvalidRequest) as ei:
        c.create_job("")
    assert ei.value.code == "empty_input"


def test_wait_done_and_failed() -> None:
    states = iter([{"id": "j", "state": "running", "rev": 1}, {"id": "j", "state": "done", "rev": 2}])
    c = _client(lambda r: httpx.Response(200, json=next(states)))
    assert c.wait("j", long_poll=None, poll_interval=0)["state"] == "done"

    c = _client(lambda r: httpx.Response(200, json={
        "id": "j", "state": "failed", "rev": 3, "error": {"code": "x", "message": "boom", "retryable": True}}))
    with pytest.raises(JobFailed) as ei:
        c.wait("j", long_poll=None)
    assert ei.value.retryable is True
