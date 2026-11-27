"""TTS 불가 재큐 상한·백오프(main.py/tts_requeue.py)와 대본 선저장(processor) 테스트 — 서버·LLM 호출 없음.

배경(4892a1b 리뷰 BUG 2): 한 글이 TTS 서버에서 500/429/대기초과를 계속 만나면 가장 오래된 APPROVED가
30초마다 재선택돼 뒤 글이 막히고, 대본이 TTS 후에만 저장돼 LLM도 매번 재호출됐다.
"""
import asyncio
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import config.settings as cfg
from ai_worker.core import main as m
from ai_worker.core import processor as proc_mod
from ai_worker.core import tts_requeue as rq
from ai_worker.tts.synth import TTSUnavailable
from db.models import Base, Content, Post, PostStatus, ScriptData

pytestmark = pytest.mark.unit

T0 = datetime(2026, 11, 27, 12, 0)
NOW = 1_800_000_000.0


@pytest.fixture()
def factory(monkeypatch):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[Post.__table__, Content.__table__])
    f = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(m, "SessionLocal", f)
    monkeypatch.setattr(proc_mod, "SessionLocal", f)
    monkeypatch.setattr(cfg, "TTS_REQUEUE_MAX", 5)
    # SQLite는 BigInteger PK 자동증가가 없어 Content.id를 직접 채우는 리스너를 둔다(테스트 전용).
    from sqlalchemy import event

    @event.listens_for(Content, "before_insert")
    def _fill_id(mapper, conn, target):
        if target.id is None:
            target.id = (conn.exec_driver_sql("select coalesce(max(id),0)+1 from contents").scalar())

    monkeypatch.setattr(cfg, "TTS_REQUEUE_BACKOFF_BASE_SEC", 30)
    monkeypatch.setattr(cfg, "TTS_REQUEUE_BACKOFF_MAX_SEC", 600)
    return f


def _add(f, pid, status=PostStatus.APPROVED, last_error=None, created=T0, site="x"):
    with f() as s:
        s.add(Post(id=pid, site_code=site, origin_id=str(pid), title="t", content="c",
                   status=status, retry_count=2, last_error=last_error,
                   created_at=created, updated_at=created))
        s.commit()


def _post(f, pid):
    with f() as s:
        return s.query(Post).filter_by(id=pid).first()


class FailingProcessor:
    async def llm_tts_stage(self, pid):
        raise TTSUnavailable("500 반복")


def _fail_once(f, pid=1):
    """llm_tts_stage 시작과 같이 PROCESSING으로 만들고(+last_error 마커 이어받기) TTS 불가를 낸다."""
    with f() as s:
        p = s.query(Post).filter_by(id=pid).first()
        p.status = PostStatus.PROCESSING
        p.last_error = rq.carry_marker(p.last_error)   # processor가 시작 시 하는 일
        s.commit()
    with pytest.raises(m._TTSRequeued) as ei:
        asyncio.run(m._run_llm_tts_supervised(FailingProcessor(), pid))
    return ei.value


# ── 백오프 수식 ──────────────────────────────────────────────────

def test_backoff_growth_and_cap(factory):
    assert [rq.backoff_sec(n) for n in (1, 2, 3, 4, 5, 6, 9)] == [30, 60, 120, 240, 480, 600, 600]
    assert rq.backoff_sec(0) == 0


def test_marker_roundtrip_expiry_and_eligibility(factory):
    note = rq.format_note(2, "사유", now=NOW)
    assert rq.parse_state(note, now=NOW + 1) == (2, NOW)
    assert not rq.is_eligible(note, now=NOW + 59) and rq.is_eligible(note, now=NOW + 61)
    assert rq.parse_state(note, now=NOW + rq.STATE_TTL_SEC + 1) == (0, 0.0)   # 만료
    assert rq.is_eligible(None) and rq.is_eligible("다른 오류 문구")
    assert rq.carry_marker(note + " 뒤따르는 문구") == note.split("]")[0] + "]"
    assert rq.carry_marker("그냥 오류") is None


# ── 재큐 카운트·상한 ──────────────────────────────────────────────

def test_requeue_counts_up_then_fails_at_cap(factory, monkeypatch):
    _add(factory, 1)
    for n in range(1, 5):                              # 1~4회째: 재큐(retry_count 유지)
        err = _fail_once(factory)
        assert err.exhausted is False
        p = _post(factory, 1)
        assert p.status == PostStatus.APPROVED and p.retry_count == 2
        assert rq.parse_state(p.last_error)[0] == n
    err = _fail_once(factory)                           # 5회째: FAILED
    assert err.exhausted is True
    p = _post(factory, 1)
    assert p.status == PostStatus.FAILED
    assert "TTS_UNAVAILABLE_EXHAUSTED" in p.last_error and "5회" in p.last_error


def test_cap_is_env_configurable(factory, monkeypatch):
    monkeypatch.setattr(cfg, "TTS_REQUEUE_MAX", 2)
    _add(factory, 1)
    assert _fail_once(factory).exhausted is False
    assert _fail_once(factory).exhausted is True
    assert _post(factory, 1).status == PostStatus.FAILED


def test_stale_marker_does_not_count(factory, monkeypatch):
    old = rq.format_note(4, "옛날", now=NOW - rq.STATE_TTL_SEC - 10)
    monkeypatch.setattr(rq.time, "time", lambda: NOW)
    _add(factory, 1, last_error=old)
    assert _fail_once(factory).exhausted is False      # 만료된 4회는 무시 → 1회째
    assert rq.parse_state(_post(factory, 1).last_error, now=NOW)[0] == 1


# ── 백오프 중 글은 건너뛰고 뒤 글을 진행 ───────────────────────────────

def test_pick_skips_backing_off_post_and_serves_next(factory):
    _add(factory, 1, last_error=rq.format_note(3, "x", now=NOW), created=T0)
    _add(factory, 2, created=datetime(2026, 11, 27, 13, 0))
    assert m._pick_next_approved(now=NOW + 10) == (2, "x")            # 1번은 120s 백오프 중
    assert m._pick_next_approved(now=NOW + 121)[0] == 1               # 지나면 오래된 글 우선 복귀


def test_pick_returns_none_when_everything_backing_off(factory):
    _add(factory, 1, last_error=rq.format_note(1, "x", now=NOW))
    assert m._pick_next_approved(now=NOW + 5) == (None, None)


def test_pick_keeps_again_spring_priority(factory):
    _add(factory, 1, created=T0, site="x")
    _add(factory, 2, created=datetime(2026, 11, 27, 14, 0), site="again_spring")
    assert m._pick_next_approved(now=NOW) == (2, "again_spring")


def test_render_stage_unavailable_shares_the_same_cap(factory):
    _add(factory, 1, status=PostStatus.PROCESSING)
    for _ in range(4):
        assert m._handle_tts_unavailable(1, 2, TTSUnavailable("t"), "렌더 중") is False
        with factory() as s:                                          # 다시 집힘
            s.query(Post).filter_by(id=1).update({"status": PostStatus.PROCESSING})
            s.commit()
    assert m._handle_tts_unavailable(1, 2, TTSUnavailable("t"), "렌더 중") is True
    assert _post(factory, 1).status == PostStatus.FAILED


# ── 대본 선저장 ───────────────────────────────────────────────────

def _script():
    return ScriptData(hook="안녕하세요 오늘의 사연", body=[{"type": "body", "lines": ["본문"]}],
                      closer="끝", title_suggestion="t", tags=[], mood="daily")


def test_script_persisted_before_tts_and_reusable(factory):
    _add(factory, 1, status=PostStatus.PROCESSING)
    with factory() as session:
        proc_mod.RobustProcessor._persist_script_before_tts(session, 1, _script(), "F4")
    with factory() as s:
        c = s.query(Content).filter_by(post_id=1).first()
        assert c.tts_voice == "F4"                       # 확정 프리셋 → 재처리에도 안정
        back = ScriptData.from_json(c.summary_text)      # 다음 시도의 "기존 대본 재사용" 경로 조건
        assert back.hook and len(back.hook) >= 5 and back.body
        assert c.audio_path is None                      # 오디오는 TTS 성공 뒤에만


def test_persist_updates_existing_content_row(factory):
    _add(factory, 1, status=PostStatus.PROCESSING)
    with factory() as s:
        s.add(Content(id=1, post_id=1, summary_text="old", tts_voice="yura"))
        s.commit()
    with factory() as session:
        proc_mod.RobustProcessor._persist_script_before_tts(session, 1, _script(), "M2")
    with factory() as s:
        c = s.query(Content).filter_by(post_id=1).first()
        assert c.tts_voice == "M2" and "안녕하세요" in c.summary_text


def test_stage_start_clears_error_but_keeps_requeue_marker():
    marker = rq.format_note(3, "r", now=NOW)
    assert rq.carry_marker(marker) is not None
    assert rq.carry_marker("LLM 오류: 뭔가") is None
