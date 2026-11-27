"""TTS 서버 일시 장애 보류/재큐(main.py)와 phase 정체 판정(progress.py) 테스트."""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from ai_worker.core import main as m
from ai_worker.core import progress
from ai_worker.core import processor as proc_mod
from ai_worker.tts.synth import TTSUnavailable
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


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    monkeypatch.setattr(m, "_tts_hold_active", False)


def _probe(monkeypatch, result):
    calls = []

    async def fake(timeout_sec=None):
        calls.append(timeout_sec)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(m, "wait_for_tts_server", fake)
    return calls


def test_hold_check_down_up_and_exception(monkeypatch):
    calls = _probe(monkeypatch, False)
    assert asyncio.run(m._tts_hold_check()) is True
    assert calls == [m._TTS_PROBE_TIMEOUT_SEC]  # 비차단(짧은 한도) 확인
    _probe(monkeypatch, True)
    assert asyncio.run(m._tts_hold_check()) is False
    _probe(monkeypatch, RuntimeError("boom"))
    assert asyncio.run(m._tts_hold_check()) is False  # fail-open


def test_hold_check_logs_only_on_state_change(monkeypatch, caplog):
    _probe(monkeypatch, False)
    with caplog.at_level("INFO", logger=m.logger.name):
        for _ in range(3):
            asyncio.run(m._tts_hold_check())
    assert sum("보류" in r.message for r in caplog.records) == 1


class FakeProcessor:
    def __init__(self, exc=None):
        self.exc = exc

    async def llm_tts_stage(self, pid):
        if self.exc:
            raise self.exc
        return ("script", "audio.wav")


def test_supervised_normal_completion_keeps_status(factory):
    res = asyncio.run(m._run_llm_tts_supervised(FakeProcessor(), 1))
    assert res == ("script", "audio.wav")
    with factory() as s:
        assert s.get(Post, 1).status == PostStatus.PROCESSING


def test_tts_unavailable_requeues_keeping_retry_count(factory):
    with pytest.raises(m._TTSRequeued):
        asyncio.run(m._run_llm_tts_supervised(FakeProcessor(TTSUnavailable("서버 불가")), 1))
    with factory() as s:
        p = s.get(Post, 1)
        assert p.status == PostStatus.APPROVED and p.retry_count == 2
        assert "재큐" in p.last_error


def test_other_errors_propagate_without_requeue(factory):
    with pytest.raises(ValueError):
        asyncio.run(m._run_llm_tts_supervised(FakeProcessor(ValueError("x")), 1))
    with factory() as s:
        assert s.get(Post, 1).status == PostStatus.PROCESSING  # FAILED 처리는 호출부 몫


def test_requeue_helper_is_conditional_on_processing(factory):
    with factory() as s:
        s.get(Post, 1).status = PostStatus.FAILED
        s.commit()
    assert m._requeue_without_retry(1, 0, "x") is False
    with factory() as s:
        assert s.get(Post, 1).status == PostStatus.FAILED


def test_phase_heartbeat_swallows_progress_errors(monkeypatch):
    """heartbeat stamp 실패가 본 작업 결과를 가리지 않는다."""
    def boom(*a, **k):
        raise RuntimeError("db down")

    monkeypatch.setattr(proc_mod, "stamp_progress", boom)

    async def run():
        real_sleep = asyncio.sleep

        async def fast(_):
            await real_sleep(0)

        monkeypatch.setattr(asyncio, "sleep", fast)

        async def work():
            for _ in range(5):
                await real_sleep(0)
            return 7

        return await proc_mod._with_phase_heartbeat(work(), 1, 5, "TTS 합성")

    assert asyncio.run(run()) == 7


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
