"""PROCESSING 고착 회수·하트비트·실패 분류 회귀 테스트 (sqlite 인메모리)."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from ai_worker.core import progress, recovery
from ai_worker.core.main import _classify_failure
from db.models import Base, Post, PostStatus

NOW = datetime(2026, 11, 25, 12, 0, tzinfo=timezone.utc)


@pytest.fixture()
def factory():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[Post.__table__])
    return sessionmaker(bind=engine, expire_on_commit=False)


def _add(factory, pid, status, retry=0, updated=None):
    with factory() as s:
        s.add(Post(
            id=pid, site_code="x", origin_id=str(pid), title="t", content="c",
            status=status, retry_count=retry,
            created_at=NOW.replace(tzinfo=None), updated_at=(updated or NOW).replace(tzinfo=None),
        ))
        s.commit()


def _status(factory, pid):
    with factory() as s:
        p = s.get(Post, pid)
        return p.status, p.last_error


def _run(factory, **kw):
    return recovery.reclaim_stuck_posts(
        session_factory=factory, heartbeat_loader=kw.pop("hb", lambda _id: None), now=NOW, **kw
    )


def test_startup_reclaims_all_and_respects_retry_limit(factory):
    _add(factory, 1, PostStatus.PROCESSING, retry=1)
    _add(factory, 2, PostStatus.PROCESSING, retry=3)  # MAX_RETRY_COUNT=3 소진
    _add(factory, 3, PostStatus.APPROVED)
    res = _run(factory, startup=True, max_retry=3)
    assert res == {"requeued": [1], "failed": [2]}
    assert _status(factory, 1)[0] == PostStatus.APPROVED
    assert _status(factory, 2)[0] == PostStatus.FAILED
    assert "소진" in _status(factory, 2)[1]
    assert _status(factory, 3)[0] == PostStatus.APPROVED


def test_periodic_skips_fresh_heartbeat_and_reclaims_stale(factory):
    old = NOW - timedelta(hours=2)
    _add(factory, 1, PostStatus.PROCESSING, updated=old)  # 하트비트 신선 → 유지
    _add(factory, 2, PostStatus.PROCESSING, updated=old)  # 하트비트 없음 + 오래됨 → 회수
    _add(factory, 3, PostStatus.PROCESSING, updated=NOW - timedelta(minutes=5))  # updated 신선
    hb = lambda pid: NOW - timedelta(minutes=1) if pid == 1 else None
    res = _run(factory, hb=hb, stale_minutes=30)
    assert res["requeued"] == [2] and res["failed"] == []
    assert _status(factory, 1)[0] == PostStatus.PROCESSING
    assert _status(factory, 3)[0] == PostStatus.PROCESSING


def test_periodic_never_touches_inflight_posts(factory):
    _add(factory, 1, PostStatus.PROCESSING, updated=NOW - timedelta(hours=5))
    res = _run(factory, exclude_ids={1}, stale_minutes=30)
    assert res == {"requeued": [], "failed": []}
    assert _status(factory, 1)[0] == PostStatus.PROCESSING


def test_naive_and_future_timestamps_do_not_raise_or_reclaim(factory):
    _add(factory, 1, PostStatus.PROCESSING, updated=NOW + timedelta(hours=9))  # 시간대 어긋난 미래값
    assert _run(factory, stale_minutes=30) == {"requeued": [], "failed": []}


def test_only_processing_rows_change(factory):
    _add(factory, 1, PostStatus.FAILED, updated=NOW - timedelta(days=3))
    _add(factory, 2, PostStatus.RENDERED, updated=NOW - timedelta(days=3))
    assert _run(factory, stale_minutes=1) == {"requeued": [], "failed": []}
    assert _status(factory, 1)[0] == PostStatus.FAILED


def test_parse_iso_handles_z_naive_and_garbage():
    assert recovery._parse_iso("2026-11-25T00:00:00Z") == datetime(2026, 11, 25, tzinfo=timezone.utc)
    assert recovery._parse_iso("2026-11-25T00:00:00").tzinfo is not None
    assert recovery._parse_iso("nope") is None and recovery._parse_iso(None) is None


def test_touch_heartbeat_uses_progress_namespace(monkeypatch):
    calls = []
    monkeypatch.setattr(progress, "touch_runtime_heartbeat", lambda pid, key: calls.append((pid, key)) or True)
    assert progress.touch_heartbeat(7) is True
    assert calls == [(7, "progress")]


def test_stamp_progress_exposes_contract_fields(monkeypatch):
    saved = {}
    monkeypatch.setattr(progress, "get_runtime_state", lambda *_: None)
    monkeypatch.setattr(progress, "put_runtime_state", lambda _p, k, v: saved.update({k: v}) or True)
    progress.stamp_progress(1, 5, "TTS 합성")
    p = saved["progress"]
    assert {"current_phase", "last_heartbeat_at", "updated_at"} <= set(p)
    datetime.fromisoformat(p["last_heartbeat_at"])


@pytest.mark.parametrize("msg,code", [
    ("OperationalError: (2006, 'MySQL server has gone away')", "INFRA_DB_DISCONNECT"),
    ("(pymysql.err.OperationalError) (2013, 'Lost connection to MySQL server during query')", "INFRA_DB_DISCONNECT"),
    ("ReadTimeout('timed out')", "INFRA_TIMEOUT"),
])
def test_transient_failures_are_classified_retryable(msg, code):
    got, _stage, retryable = _classify_failure(msg)
    assert got == code and retryable is True
