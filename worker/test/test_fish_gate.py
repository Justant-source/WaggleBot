"""fish_gate 단위 테스트 — 가짜 health/ask/sleep/clock 주입, 네트워크·DB 없음."""
import asyncio

import pytest

from ai_worker.tts.fish_gate import FishGate, FishGateTimeout


class _Env:
    """가짜 시계 + sleep(시계를 전진시키고 훅 실행) + 스크립트된 응답."""

    def __init__(self, asks=None, health_after=None):
        self.now = 0.0
        self.asks = list(asks or [])
        self.ask_times: list[float] = []
        self.health_after = health_after  # 이 시각 이후 healthy (None=계속 down)
        self.stamps: list[tuple[int, int, str]] = []

    async def health(self) -> bool:
        return self.health_after is not None and self.now >= self.health_after

    async def ask(self):
        self.ask_times.append(self.now)
        if not self.asks:
            return None
        r = self.asks.pop(0) if len(self.asks) > 1 else self.asks[0]
        if isinstance(r, Exception):
            return None
        return r

    async def sleep(self, sec: float) -> None:
        self.now += sec

    def gate(self, **kw) -> FishGate:
        defaults = dict(
            health=self.health, ask=self.ask, sleep=self.sleep, clock=lambda: self.now,
            progress=lambda p, ph, label: self.stamps.append((p, ph, label)),
            enabled=True, recheck_sec=1800, max_wait_sec=86400,
            heartbeat_sec=30, start_poll_sec=10, start_max_sec=360,
        )
        defaults.update(kw)
        return FishGate(**defaults)


def run(coro):
    return asyncio.run(coro)


def test_healthy_skips_gate():
    env = _Env(health_after=0)
    run(env.gate().ensure_ready())
    assert env.ask_times == []


def test_disabled_does_nothing():
    env = _Env()
    run(env.gate(enabled=False).ensure_ready())
    assert env.ask_times == []


def test_starting_polls_health_every_10s():
    env = _Env(asks=[{"state": "starting"}], health_after=35)
    run(env.gate().ensure_ready())
    assert env.ask_times == [0.0]
    assert 35 <= env.now <= 45


def test_starting_timeout_reasks():
    env = _Env(asks=[{"state": "starting"}], health_after=500)
    run(env.gate().ensure_ready())
    assert len(env.ask_times) >= 2  # 6분 폴링 실패 후 재질의


def test_blocked_waits_and_rechecks_every_30min_with_heartbeat():
    env = _Env(
        asks=[{"state": "blocked", "reason": "xplane", "retry_after_sec": 600},
              {"state": "blocked", "reason": "xplane"},
              {"state": "ready"}],
        health_after=3700,
    )
    g = env.gate()
    g.bind_post(7, 5, "TTS 합성")
    run(g.ensure_ready())
    assert env.ask_times[:3] == [0.0, 1800.0, 3600.0]
    labels = [s[2] for s in env.stamps]
    assert any("TTS 대기: X-Plane 실행 중 — 30분마다 재확인" == l for l in labels)
    # heartbeat는 30초 간격으로 갱신되어 정체로 보이지 않는다
    assert len(env.stamps) > 100
    assert env.stamps[-1][2] == "TTS 합성"  # 종료 시 원래 phase 문구 복원
    assert g.wait_label(7) is None


def test_health_during_sleep_proceeds_immediately():
    env = _Env(asks=[{"state": "blocked", "reason": "xplane"}], health_after=100)
    run(env.gate().ensure_ready())
    assert env.ask_times == [0.0]
    assert env.now < 200


def test_gate_unreachable_falls_back_to_health_only():
    env = _Env(asks=[], health_after=5000)  # ask -> None
    g = env.gate()
    run(g.ensure_ready())
    assert env.ask_times == [0.0, 1800.0, 3600.0, 5400.0][:len(env.ask_times)]
    assert 5000 <= env.now < 5100


def test_unavailable_label():
    env = _Env(asks=[{"state": "unavailable"}], health_after=60)
    g = env.gate()
    g.bind_post(1, 5, "TTS 합성")
    run(g.ensure_ready())
    assert any("GPU 데몬 없음" in s[2] for s in env.stamps)


def test_max_wait_raises_timeout():
    env = _Env(asks=[{"state": "blocked", "reason": "xplane"}], health_after=None)
    with pytest.raises(FishGateTimeout):
        run(env.gate(max_wait_sec=7200).ensure_ready())
    assert env.now >= 7200


def test_recover_returns_false_when_healthy():
    env = _Env(health_after=0)
    assert run(env.gate().recover("x")) is False


def test_recover_waits_when_fish_down_then_true():
    env = _Env(asks=[{"state": "starting"}], health_after=20)
    assert run(env.gate().recover("x")) is True


def test_should_skip_start_only_when_blocked():
    for resp, expected in [
        ({"state": "blocked", "reason": "xplane"}, True),
        ({"state": "ready"}, False),
        ({"state": "unavailable"}, False),
        (None, False),
    ]:
        env = _Env(asks=[resp] if resp else [])
        assert run(env.gate().should_skip_start()) is expected


def test_health_success_cached_20s():
    calls = []

    async def health():
        calls.append(1)
        return True

    env = _Env()
    g = env.gate(health=health)
    run(g.ensure_ready())
    run(g.ensure_ready())
    assert len(calls) == 1
    env.now += 25
    run(g.ensure_ready())
    assert len(calls) == 2


# ── fish_client._request_one 통합(가짜 client/gate) ──────────────
class _Resp:
    content = b"WAV"

    def raise_for_status(self) -> None:
        return None


class _FlakyClient:
    def __init__(self, errors):
        self.errors = list(errors)
        self.calls = 0

    async def post(self, url, json=None):
        self.calls += 1
        if self.errors:
            raise self.errors.pop(0)
        return _Resp()


class _FakeGate:
    enabled = True

    def __init__(self, waited=True):
        self.waited = waited
        self.reasons: list[str] = []

    async def recover(self, why):
        self.reasons.append(why)
        return self.waited


def test_request_one_retries_after_gate_wait_on_connect_error(monkeypatch):
    import httpx
    from ai_worker.tts import fish_client

    fake = _FakeGate()
    monkeypatch.setattr(fish_client, "_fish_gate", fake)
    client = _FlakyClient([httpx.ConnectError("down")])
    assert run(fish_client._request_one(client, {})) == b"WAV"
    assert client.calls == 2 and len(fake.reasons) == 1


def test_request_one_raises_when_fish_alive(monkeypatch):
    import httpx
    from ai_worker.tts import fish_client

    monkeypatch.setattr(fish_client, "_fish_gate", _FakeGate(waited=False))
    with pytest.raises(httpx.ConnectError):
        run(fish_client._request_one(_FlakyClient([httpx.ConnectError("x")]), {}))


def test_request_one_final_read_timeout_waits_then_retries(monkeypatch):
    import httpx
    from ai_worker.tts import fish_client

    fake = _FakeGate()
    monkeypatch.setattr(fish_client, "_fish_gate", fake)
    errs = [httpx.ReadTimeout("t")] * (fish_client._MAX_TTS_RETRIES + 1)
    client = _FlakyClient(errs)
    assert run(fish_client._request_one(client, {})) == b"WAV"
    assert len(fake.reasons) == 1
