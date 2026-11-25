"""Fish 차단 보류/재큐(main.py)와 phase 정체 판정(progress.py) 테스트."""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from ai_worker.core import main as m
from ai_worker.core import progress
from db.models import Base, Post, PostStatus

NOW = datetime(2026, 11, 25, 12, 0, tzinfo=timezone.utc)


@pytest.fixture()
def factory(monkeypatch):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[Post.__table__])
    f = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(m, "SessionLocal", f)
    with f() as s:
        s.add(Post(id=1, site_code="x", origin_id="1", title="t", content="c",
                   status=PostStatus.PROCESSING, retry_count=2,
                   created_at=NOW.replace(tzinfo=None), updated_at=NOW.replace(tzinfo=None)))
        s.commit()
    return f


class FakeGate:
    def __init__(self, reason=None, label=None, raises=False):
        self.reason, self.label, self.raises = reason, label, raises
        self.unbound = []

    async def blocked_reason(self):
        if self.raises:
            raise RuntimeError("boom")
        return self.reason

    def wait_label(self, pid):
        return self.label

    def unbind_post(self, pid=None):
        self.unbound.append(pid)


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    monkeypatch.setattr(m, "_fish_hold_reason", None)


def test_hold_check_blocked_none_and_exception(monkeypatch):
    monkeypatch.setattr(m, "fish_gate", FakeGate(reason="xplane"))
    assert asyncio.run(m._fish_hold_check()) == "xplane"
    monkeypatch.setattr(m, "fish_gate", FakeGate(reason=None))
    assert asyncio.run(m._fish_hold_check()) is None
    monkeypatch.setattr(m, "fish_gate", FakeGate(raises=True))
    assert asyncio.run(m._fish_hold_check()) is None  # fail-open


def test_hold_check_logs_only_on_state_change(monkeypatch, caplog):
    monkeypatch.setattr(m, "fish_gate", FakeGate(reason="xplane"))
    with caplog.at_level("INFO", logger=m.logger.name):
        for _ in range(3):
            asyncio.run(m._fish_hold_check())
    assert sum("보류" in r.message for r in caplog.records) == 1


class FakeProcessor:
    def __init__(self, delay=None):
        self.delay, self.cancelled = delay, False

    async def llm_tts_stage(self, pid):
        if self.delay is None:
            return ("script", "audio.wav")
        try:
            await asyncio.sleep(self.delay)
        except asyncio.CancelledError:
            self.cancelled = True
            raise
        return ("script", "audio.wav")


def test_supervised_normal_completion_keeps_status(factory, monkeypatch):
    monkeypatch.setattr(m, "fish_gate", FakeGate(reason="xplane", label=None))
    res = asyncio.run(m._run_llm_tts_supervised(FakeProcessor(), 1, check_interval=0.01))
    assert res == ("script", "audio.wav")
    with factory() as s:
        assert s.get(Post, 1).status == PostStatus.PROCESSING


def _run_blocked(factory, monkeypatch, gate, requeue_after, ticks):
    t = {"v": 0.0}

    def clock():
        t["v"] += ticks
        return t["v"]

    monkeypatch.setattr(m, "fish_gate", gate)
    proc = FakeProcessor(delay=5)
    return proc, lambda: asyncio.run(
        m._run_llm_tts_supervised(proc, 1, requeue_after=requeue_after, check_interval=0.01, clock=clock)
    )


def test_requeue_when_blocked_long_keeps_retry_count(factory, monkeypatch):
    proc, run = _run_blocked(factory, monkeypatch, FakeGate(reason="xplane", label="TTS 대기"), 600, 400)
    with pytest.raises(m._FishRequeued):
        run()
    assert proc.cancelled
    with factory() as s:
        p = s.get(Post, 1)
        assert p.status == PostStatus.APPROVED and p.retry_count == 2
        assert "재큐" in p.last_error


def test_no_requeue_before_threshold_or_when_not_blocked(factory, monkeypatch):
    # 임계 미만: 계속 대기하다 정상 완료(짧은 delay)
    monkeypatch.setattr(m, "fish_gate", FakeGate(reason="xplane", label="TTS 대기"))
    proc = FakeProcessor(delay=0.05)
    res = asyncio.run(m._run_llm_tts_supervised(proc, 1, requeue_after=10_000, check_interval=0.01))
    assert res and not proc.cancelled
    # 임계 초과여도 blocked가 아니면 취소하지 않는다
    monkeypatch.setattr(m, "fish_gate", FakeGate(reason=None, label="TTS 대기"))
    proc = FakeProcessor(delay=0.05)
    res = asyncio.run(m._run_llm_tts_supervised(proc, 1, requeue_after=0, check_interval=0.01))
    assert res and not proc.cancelled
    with factory() as s:
        assert s.get(Post, 1).status == PostStatus.PROCESSING


def test_requeue_helper_is_conditional_on_processing(factory):
    with factory() as s:
        s.get(Post, 1).status = PostStatus.FAILED
        s.commit()
    assert m._requeue_without_retry(1, 0, "x") is False
    with factory() as s:
        assert s.get(Post, 1).status == PostStatus.FAILED


# ── D: phase 정체 판정 ──────────────────────────────────────
def _st(delta, **kw):
    return {"stamped_at": (NOW - timedelta(seconds=delta)).isoformat(), **kw}


def test_phase_stalled_boundary():
    assert progress.phase_stalled(_st(7200), NOW, 7200) is False  # 정확히 상한 = 아직 정체 아님
    assert progress.phase_stalled(_st(7201), NOW, 7200) is True
    assert progress.phase_stalled(_st(10), NOW, 7200) is False


def test_phase_stalled_conservative_cases():
    assert progress.phase_stalled(None, NOW, 1) is False
    assert progress.phase_stalled({}, NOW, 1) is False  # stamped_at 없는 레거시
    assert progress.phase_stalled(_st(99999, done=True), NOW, 1) is False  # 큐 대기
    assert progress.phase_stalled({"stamped_at": "garbage"}, NOW, 1) is False
    assert progress.phase_stalled(_st(99999), NOW, 0) is False  # 비활성


def test_phase_stalled_naive_and_aware_mix():
    naive_state = {"stamped_at": (NOW - timedelta(hours=3)).replace(tzinfo=None).isoformat()}
    assert progress.phase_stalled(naive_state, NOW, 7200) is True
    assert progress.phase_stalled(naive_state, NOW.replace(tzinfo=None), 7200) is True
    z = {"stamped_at": (NOW - timedelta(seconds=5)).strftime("%Y-%m-%dT%H:%M:%SZ")}
    assert progress.phase_stalled(z, NOW, 7200) is False


def test_touch_unless_stalled(monkeypatch):
    touched = []
    monkeypatch.setattr(progress, "touch_heartbeat", lambda pid: touched.append(pid) or True)
    fresh = {"stamped_at": datetime.now(timezone.utc).isoformat()}
    monkeypatch.setattr(progress, "get_runtime_state", lambda *_: fresh)
    assert progress.touch_heartbeat_unless_stalled(5, 7200) == "touched"
    old = {"stamped_at": (datetime.now(timezone.utc) - timedelta(hours=9)).isoformat()}
    monkeypatch.setattr(progress, "get_runtime_state", lambda *_: old)
    assert progress.touch_heartbeat_unless_stalled(5, 7200) == "stalled"
    assert touched == [5]


def test_stamp_progress_sets_stamped_at(monkeypatch):
    saved = {}
    monkeypatch.setattr(progress, "get_runtime_state", lambda *_: None)
    monkeypatch.setattr(progress, "put_runtime_state", lambda _p, k, v: saved.update({k: v}) or True)
    progress.stamp_progress(1, 2, "대본 생성")
    assert saved["progress"]["stamped_at"] == saved["progress"]["updated_at"]
