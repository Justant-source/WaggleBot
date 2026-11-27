"""ai_worker.tts.synth 단위 테스트 — 서버 없이 httpx.MockTransport 주입."""
import asyncio
import json

import httpx
import pytest

from ai_worker.tts import synth
from ai_worker.tts.local_tts_client import LocalTTS

pytestmark = pytest.mark.unit

WAV = b"RIFF....WAVEfake"


class FakeServer:
    def __init__(self, *, create_status=202, job_state="done", job_error=None, ready=True,
                 create_failures=0):
        self.requests: list[httpx.Request] = []
        self.create_status = create_status
        self.job_state = job_state
        self.job_error = job_error
        self.ready = ready
        self.create_failures = create_failures

    def __call__(self, req: httpx.Request) -> httpx.Response:
        self.requests.append(req)
        p = req.url.path
        if req.method == "POST" and p == "/v1/jobs":
            if self.create_failures > 0:
                self.create_failures -= 1
                return httpx.Response(429, headers={"retry-after": "0"}, json={"error": {"code": "queue_full"}})
            if self.create_status != 202:
                return httpx.Response(self.create_status, json={"error": {"code": "queue_full" if self.create_status == 429 else "x", "message": "m"}})
            return httpx.Response(202, json={"id": "job1", "state": "queued"})
        if req.method == "GET" and p == "/v1/jobs/job1":
            body = {"id": "job1", "state": self.job_state, "rev": 1, "result": {"duration_sec": 1.5}}
            if self.job_error:
                body["error"] = self.job_error
            return httpx.Response(200, json=body)
        if p == "/v1/jobs/job1/audio":
            return httpx.Response(200, content=WAV)
        if p == "/readyz":
            return httpx.Response(200 if self.ready else 503, json={})
        return httpx.Response(200, json={})   # delete / cancel

    def create_body(self) -> dict:
        req = next(r for r in self.requests if r.method == "POST" and r.url.path == "/v1/jobs")
        return json.loads(req.content)


@pytest.fixture
def server(monkeypatch):
    srv = FakeServer()

    def install(s: FakeServer, retries: int = 2):
        monkeypatch.setattr(synth, "_new_client", lambda: LocalTTS(
            "http://tts.test", client="wagglebot", transport=httpx.MockTransport(s),
            sleep=lambda x: None, max_retries=retries))
        return s

    monkeypatch.setattr(synth, "prenormalize", lambda t: t)
    monkeypatch.setattr(synth, "resolve_voice", lambda key, post_id=None: "F3")
    monkeypatch.setattr(synth._cfg, "TTS_PROFILE", "wagglebot/shorts-ko")
    monkeypatch.setattr(synth._cfg, "TTS_SPEED", 1.05)
    monkeypatch.setattr(synth._cfg, "TTS_SERVER_MAX_WAIT_SEC", 5)
    install(srv)
    srv.install = install
    return srv


def run(coro):
    return asyncio.run(coro)


def test_request_body_shape_and_wav_saved(server, tmp_path) -> None:
    out = run(synth.synthesize("안녕하세요 3.5%", scene_type="intro", voice_key="yura",
                               output_path=tmp_path / "a" / "x.wav", emotion="sad", post_id=42))
    assert out.read_bytes() == WAV
    body = server.create_body()
    o = body["options"]
    assert body["input"] == "안녕하세요 3.5%"
    assert o["voice"] == "F3" and o["lang"] == "ko" and o["speed"] == 1.05
    assert o["normalize"]["profile"] == "wagglebot/shorts-ko"
    assert o["chunk"] == {"mode": "max_chars", "max_chars": 120}
    assert o["postprocess"]["loudnorm"]["i"] == -16
    assert o["output"]["format"] == "wav"
    assert "request_id" not in body                       # 최상위 금지
    assert o["request_id"].startswith("wb-42-intro-")     # options 안, post_id·scene 포함
    post = next(r for r in server.requests if r.url.path == "/v1/jobs" and r.method == "POST")
    assert post.headers["x-client-id"] == "wagglebot"
    assert post.headers["idempotency-key"] == o["request_id"]   # 서버 규칙: 둘이 같아야 함


def test_profile_omitted_when_unset(server, monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(synth._cfg, "TTS_PROFILE", "")
    run(synth.synthesize("테스트", output_path=tmp_path / "x.wav"))
    assert "profile" not in server.create_body()["options"]["normalize"]


def test_emotion_ignored(server, tmp_path) -> None:
    run(synth.synthesize("테스트", emotion="sad", output_path=tmp_path / "x.wav"))
    assert "(sad)" not in server.create_body()["input"]


@pytest.mark.parametrize("text", ["", "   ", "...", "ㅋㅋㅋ", "!?"])
def test_empty_text_raises_value_error(server, text, tmp_path) -> None:
    with pytest.raises(ValueError):
        run(synth.synthesize(text, output_path=tmp_path / "x.wav"))
    assert not server.requests          # 서버 호출 없음


def test_prenormalized_text_is_what_is_sent(server, monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(synth, "prenormalize", lambda t: "정리된 문장")
    run(synth.synthesize("원문 #태그", output_path=tmp_path / "x.wav"))
    assert server.create_body()["input"] == "정리된 문장"


def test_queue_full_retried_then_ok(server, tmp_path) -> None:
    server.install(FakeServer(create_failures=2), retries=3)
    assert run(synth.synthesize("테스트", output_path=tmp_path / "x.wav")).exists()


@pytest.mark.parametrize("status", [429, 503, 500])
def test_exhausted_server_errors_become_tts_unavailable(server, status, tmp_path) -> None:
    server.install(FakeServer(create_status=status), retries=1)
    with pytest.raises(synth.TTSUnavailable):
        run(synth.synthesize("테스트", output_path=tmp_path / "x.wav"))
    assert not (tmp_path / "x.wav").exists()


def test_connection_refused_is_tts_unavailable(monkeypatch, tmp_path) -> None:
    def boom(req):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(synth, "prenormalize", lambda t: t)
    monkeypatch.setattr(synth, "resolve_voice", lambda k, p=None: "M1")
    monkeypatch.setattr(synth, "_new_client", lambda: LocalTTS(
        "http://tts.test", transport=httpx.MockTransport(boom), sleep=lambda x: None, max_retries=1))
    with pytest.raises(synth.TTSUnavailable):
        run(synth.synthesize("테스트", output_path=tmp_path / "x.wav"))


def test_job_failed_retryable_vs_permanent(server, tmp_path) -> None:
    server.install(FakeServer(job_state="failed", job_error={"code": "gpu", "message": "oom", "retryable": True}))
    with pytest.raises(synth.TTSUnavailable):
        run(synth.synthesize("테스트", output_path=tmp_path / "x.wav"))
    server.install(FakeServer(job_state="failed", job_error={"code": "bad", "message": "no", "retryable": False}))
    with pytest.raises(synth.TTSError):
        run(synth.synthesize("테스트", output_path=tmp_path / "x.wav"))


def test_wait_timeout_cancels_job_and_is_unavailable(server, monkeypatch, tmp_path) -> None:
    srv = server.install(FakeServer(job_state="running"))
    monkeypatch.setattr(synth._cfg, "TTS_SERVER_MAX_WAIT_SEC", 0.01)
    with pytest.raises(synth.TTSUnavailable):
        run(synth.synthesize("테스트", output_path=tmp_path / "x.wav"))
    assert any(r.url.path == "/v1/jobs/job1:cancel" for r in srv.requests)


def test_wait_for_tts_server(server, monkeypatch) -> None:
    assert run(synth.wait_for_tts_server(1)) is True
    server.install(FakeServer(ready=False))
    monkeypatch.setattr(synth, "_READY_POLL_SEC", 0.01)
    assert run(synth.wait_for_tts_server(0.05)) is False
