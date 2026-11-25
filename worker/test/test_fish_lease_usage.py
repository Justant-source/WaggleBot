"""fish_client의 GPU 데몬 임대 사용 범위 — 실제 /v1/tts 요청 구간에만, 대기 중에는 풀고 재시도 때 다시 잡는다."""
import asyncio
from contextlib import asynccontextmanager

import httpx
import pytest

from ai_worker.tts import fish_client
from ai_worker.tts.fish_gate import FishGateTimeout


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class _Resp:
    content = b"WAV"

    def raise_for_status(self):
        return None


class _Gate:
    enabled = True

    def __init__(self, events, recover_results=(True,), max_wait_sec=None, on_recover=None):
        self.events = events
        self.results = list(recover_results)
        self.max_wait_sec = max_wait_sec
        self.on_recover = on_recover
        self.held = 0

    @asynccontextmanager
    async def lease(self, why):
        self.events.append(("acquire", why))
        self.held += 1
        try:
            yield
        finally:
            self.held -= 1
            self.events.append(("release", why))

    async def recover(self, why):
        self.events.append(("recover", self.held))  # 대기 중 임대 보유 수(0이어야 함)
        if self.on_recover:
            self.on_recover()
        return self.results.pop(0)


class _Client:
    def __init__(self, events, errors):
        self.events, self.errors = events, list(errors)

    async def post(self, url, json=None):
        self.events.append("post")
        if self.errors:
            raise self.errors.pop(0)
        return _Resp()


def test_lease_wraps_only_post(monkeypatch):
    ev = []
    monkeypatch.setattr(fish_client, "_fish_gate", _Gate(ev))
    assert run(fish_client._request_one(_Client(ev, []), {})) == b"WAV"
    assert ev == [("acquire", "tts"), "post", ("release", "tts")]


def test_lease_released_on_exception(monkeypatch):
    ev = []
    gate = _Gate(ev)
    monkeypatch.setattr(fish_client, "_fish_gate", gate)
    err = httpx.HTTPStatusError("x", request=None, response=type("R", (), {"status_code": 400})())
    with pytest.raises(httpx.HTTPStatusError):
        run(fish_client._request_one(_Client(ev, [err]), {}))
    assert gate.held == 0 and ev[-1] == ("release", "tts")


def test_lease_released_during_recover_and_reacquired(monkeypatch):
    ev = []
    monkeypatch.setattr(fish_client, "_fish_gate", _Gate(ev))
    assert run(fish_client._request_one(_Client(ev, [httpx.ConnectError("d")]), {})) == b"WAV"
    assert ev == [
        ("acquire", "tts"), "post", ("release", "tts"),
        ("recover", 0),
        ("acquire", "tts"), "post", ("release", "tts"),
    ]


def test_fish_alive_reraises_original_without_lease_leak(monkeypatch):
    ev = []
    gate = _Gate(ev, recover_results=(False,))
    monkeypatch.setattr(fish_client, "_fish_gate", gate)
    with pytest.raises(httpx.ConnectError):
        run(fish_client._request_one(_Client(ev, [httpx.ConnectError("x")]), {}))
    assert gate.held == 0


def test_combined_deadline_raises_gate_timeout(monkeypatch):
    ev = []
    now = [1000.0]
    monkeypatch.setattr(fish_client, "_monotonic", lambda: now[0])
    gate = _Gate(ev, recover_results=(True, True, True), max_wait_sec=100,
                 on_recover=lambda: now.__setitem__(0, now[0] + 60))
    monkeypatch.setattr(fish_client, "_fish_gate", gate)
    errs = [httpx.ConnectError("d")] * 3
    with pytest.raises(FishGateTimeout):
        run(fish_client._request_one(_Client(ev, errs), {}))
    # 1차 대기 60s + 2차 대기 시작 시 잔여 40s → 대기 후 3차 진입 시 잔여 <=0 → 타임아웃
    assert ev.count(("recover", 0)) == 2 and gate.held == 0


def test_no_lease_attr_is_noop(monkeypatch):
    class Plain:
        enabled = False

    monkeypatch.setattr(fish_client, "_fish_gate", Plain())
    assert run(fish_client._request_one(_Client([], []), {})) == b"WAV"


def test_synthesize_no_lease_without_request(monkeypatch, tmp_path):
    """합성 호출이 없으면(캐시 히트 경로 = synthesize 미호출) 임대도 없다: ensure_ready 단계는 임대 밖."""
    ev = []

    class G(_Gate):
        async def ensure_ready(self, **kw):
            ev.append("ensure_ready")

    monkeypatch.setattr(fish_client, "_fish_gate", G(ev))
    monkeypatch.setattr(fish_client, "_warmup_done", True)
    with pytest.raises(ValueError):
        run(fish_client.synthesize("   ", output_path=tmp_path / "a.wav"))
    assert ev == ["ensure_ready"]  # 정규화 단계 실패 — 임대 없음
