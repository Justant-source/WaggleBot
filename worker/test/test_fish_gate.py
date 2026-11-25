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
    # 첫 응답 retry_after_sec=600 → 10분 뒤, 이후 값 없음 → 기본 30분
    assert env.ask_times[:3] == [0.0, 600.0, 2400.0]
    labels = [s[2] for s in env.stamps]
    assert any("TTS 대기: X-Plane 실행 중 — 10분마다 재확인" == l for l in labels)
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


# ── 바인딩 수명주기·대기 중 heartbeat ─────────────────────────
def test_unbind_post_only_clears_matching_binding():
    env = _Env()
    g = env.gate()
    g.bind_post(2, 8, "FFmpeg 렌더링")  # 나중에 바인딩된 다른 post
    g.unbind_post(1)                    # 먼저 끝난 post의 해제는 남의 바인딩을 지우면 안 된다
    g._stamp("대기")
    assert env.stamps == [(2, 8, "대기")]
    g.unbind_post(2)
    g._stamp("대기2")
    assert env.stamps == [(2, 8, "대기")]  # 해제 후에는 progress를 쓰지 않는다


def test_unbind_post_without_id_clears_unconditionally():
    env = _Env()
    g = env.gate()
    g.bind_post(1, 5, "TTS 합성")
    g.unbind_post()
    assert g.wait_label(1) is None
    g._stamp("x")
    assert env.stamps == []


def test_wait_heartbeats_every_interval_and_clears_label_on_timeout():
    env = _Env(asks=[{"state": "blocked", "reason": "xplane"}], health_after=None)
    g = env.gate(max_wait_sec=600)
    g.bind_post(7, 5, "TTS 합성")
    with pytest.raises(FishGateTimeout):
        run(g.ensure_ready())
    waiting = [s for s in env.stamps if s[2].startswith("TTS 대기")]
    assert len(waiting) >= 600 // 30 - 1  # 30초마다 heartbeat
    assert g.wait_label(7) is None        # 타임아웃 후 대기 라벨이 남지 않는다
    assert env.now <= 600 + 30            # 상한을 크게 넘겨 자지 않는다


def test_phase_heartbeat_survives_stamp_failure(monkeypatch):
    """heartbeat 태스크의 DB 오류가 본 작업 결과를 가리지 않는다."""
    pytest.importorskip("ai_worker.core.processor")
    from ai_worker.core import processor

    calls = []

    def boom(*a, **kw):
        calls.append(a)
        raise RuntimeError("db down")

    monkeypatch.setattr(processor, "stamp_progress", boom)
    real_sleep = asyncio.sleep

    async def fast_sleep(sec):
        await real_sleep(0)

    monkeypatch.setattr(asyncio, "sleep", fast_sleep)

    async def work():
        for _ in range(5):
            await real_sleep(0)
        return "ok"

    assert run(processor._with_phase_heartbeat(work(), 1, 5, "TTS 합성")) == "ok"
    assert calls


# ── C: retry_after 클램프 ───────────────────────────────────
def test_retry_after_clamped_to_min_and_max():
    env = _Env(asks=[{"state": "blocked", "reason": "xplane", "retry_after_sec": 5},
                     {"state": "blocked", "reason": "xplane", "retry_after_sec": 99999},
                     {"state": "ready"}], health_after=2000)
    g = env.gate(min_recheck_sec=30)
    g.bind_post(1, 5, "TTS")
    run(g.ensure_ready())
    assert env.ask_times[:3] == [0.0, 30.0, 1830.0]
    assert any("30초마다 재확인" in s[2] for s in env.stamps)


def test_retry_after_ignored_when_not_blocked():
    env = _Env(asks=[{"state": "unavailable", "retry_after_sec": 60}, {"state": "ready"}], health_after=2000)
    run(env.gate().ensure_ready())
    assert env.ask_times[:2] == [0.0, 1800.0]


# ── blocked_reason ──────────────────────────────────────────
@pytest.mark.parametrize("resp,reason", [
    ({"state": "blocked", "reason": "xplane"}, "xplane"),
    ({"state": "ready"}, None),
    ({"state": "starting"}, None),
    ({"state": "unavailable"}, None),
    (None, None),
])
def test_blocked_reason_branches(resp, reason):
    env = _Env(asks=[resp] if resp else [])
    g = env.gate()
    g.bind_post(1, 5, "TTS")
    assert run(g.blocked_reason()) == reason
    assert env.stamps == [] and env.now == 0.0  # 부작용 없음


def test_blocked_reason_none_when_healthy_or_disabled():
    env = _Env(asks=[{"state": "blocked", "reason": "xplane"}], health_after=0)
    assert run(env.gate().blocked_reason()) is None
    assert env.ask_times == []
    assert run(env.gate(enabled=False).blocked_reason()) is None


# ── lease ───────────────────────────────────────────────────
class _Lease:
    def __init__(self, open_resp=None, beat_resp=None, open_exc=None, close_exc=None):
        self.calls: list[tuple] = []
        self.open_resp = {"state": "leased", "lease_id": "L1", "ttl_sec": 90} if open_resp is None else open_resp
        self.beat_resp = beat_resp or {"alive": True, "revoked": False}
        self.open_exc, self.close_exc = open_exc, close_exc
        self.n = 0

    async def open(self, why):
        self.calls.append(("open", why))
        if self.open_exc:
            raise self.open_exc
        self.n += 1
        r = dict(self.open_resp)
        if r.get("lease_id"):
            r["lease_id"] = f"L{self.n}"
        return r

    async def beat(self, lid):
        self.calls.append(("beat", lid))
        return self.beat_resp

    async def close(self, lid):
        self.calls.append(("close", lid))
        if self.close_exc:
            raise self.close_exc

    def gate(self, **kw):
        async def lsleep(sec):
            await asyncio.sleep(0)  # 양보만 — 실제 시간은 쓰지 않는다
        d = dict(enabled=True, lease_enabled=True, lease_open=self.open, lease_beat=self.beat,
                 lease_close=self.close, lease_sleep=lsleep)
        d.update(kw)
        return _Env().gate(**d)


def test_lease_open_heartbeat_release_order():
    L = _Lease()
    g = L.gate()

    async def body():
        async with g.lease("TTS"):
            for _ in range(5):
                await asyncio.sleep(0)
    run(body())
    kinds = [c[0] for c in L.calls]
    assert kinds[0] == "open" and kinds[-1] == "close" and "beat" in kinds
    assert L.calls[0] == ("open", "TTS") and L.calls[-1] == ("close", "L1")
    assert kinds.count("close") == 1


def test_lease_released_on_exception():
    L = _Lease()
    g = L.gate()

    async def body():
        async with g.lease("x"):
            raise ValueError("boom")
    with pytest.raises(ValueError):
        run(body())
    assert L.calls[-1] == ("close", "L1")


def test_lease_released_on_cancel():
    L = _Lease()
    g = L.gate()

    async def body():
        async def inner():
            async with g.lease("x"):
                await asyncio.sleep(10)
        t = asyncio.ensure_future(inner())
        await asyncio.sleep(0.01)
        t.cancel()
        with pytest.raises(asyncio.CancelledError):
            await t
    run(body())
    assert L.calls[-1] == ("close", "L1")


@pytest.mark.parametrize("kw", [
    dict(open_resp={"state": "unavailable"}),
    dict(open_exc=RuntimeError("down")),
    dict(open_resp={"state": "leased"}),  # lease_id 없음
])
def test_lease_failure_never_blocks_body(kw):
    L = _Lease(**kw)
    g = L.gate()
    ran = []

    async def body():
        async with g.lease("x"):
            ran.append(1)
    run(body())
    assert ran == [1]
    assert all(c[0] == "open" for c in L.calls)  # heartbeat·release 없음


def test_lease_release_failure_swallowed():
    L = _Lease(close_exc=RuntimeError("net"))
    g = L.gate()

    async def body():
        async with g.lease("x"):
            pass
    run(body())
    assert L.calls[-1] == ("close", "L1")


def test_lease_disabled_is_noop():
    for kw in (dict(enabled=False), dict(lease_enabled=False)):
        L = _Lease()
        g = L.gate(**kw)

        async def body():
            async with g.lease("x"):
                pass
        run(body())
        assert L.calls == []


def test_lease_revoked_warns_and_continues(caplog):
    L = _Lease(beat_resp={"alive": True, "revoked": True, "revoke_reason": "xplane"})
    g = L.gate()
    ran = []

    async def body():
        async with g.lease("x"):
            for _ in range(5):
                await asyncio.sleep(0)
            ran.append(1)
    with caplog.at_level("WARNING", logger="ai_worker.tts.fish_gate"):
        run(body())
    assert ran == [1]
    assert sum("임대 회수 통보" in r.message for r in caplog.records) == 1  # 한 번만 경고
    assert L.calls[-1][0] == "close"


def test_lease_nested_and_concurrent_release_all():
    L = _Lease()
    g = L.gate()

    async def one(name):
        async with g.lease(name):
            await asyncio.sleep(0)

    async def body():
        async with g.lease("outer"):
            await asyncio.gather(one("a"), one("b"))
    run(body())
    opened = [c[1] for c in L.calls if c[0] == "open"]
    closed = [c[1] for c in L.calls if c[0] == "close"]
    assert len(opened) == 3 and sorted(closed) == ["L1", "L2", "L3"]
