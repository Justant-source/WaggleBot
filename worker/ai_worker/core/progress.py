"""파이프라인 진행 상황 스탬프 헬퍼 — Content.pipeline_state 'progress' 키 관리."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_CHECKPOINT_KEYS = frozenset({"phase", "video_scenes_done", "video_clips", "total_scenes"})


def stamp_progress(
    post_id: int,
    phase: int,
    phase_name: str,
    *,
    scenes_done: int | None = None,
    total_scenes: int | None = None,
    done: bool = False,
) -> None:
    """Content.pipeline_state['progress'] 를 머지 방식으로 갱신. 실패 시 비치명."""
    try:
        from db.session import SessionLocal
        from db.models import Content

        now = datetime.now(timezone.utc).isoformat()

        with SessionLocal() as db:
            ct = db.query(Content).filter_by(post_id=post_id).first()
            if ct is None:
                ct = Content(post_id=post_id)
                db.add(ct)

            state: dict = dict(ct.pipeline_state or {})
            prev_progress: dict = state.get("progress") or {}

            # 동일 phase면 시작 시각 유지
            if prev_progress.get("current_phase") == phase:
                started_at = prev_progress.get("phase_started_at", now)
            else:
                started_at = now

            progress: dict = {
                "current_phase": phase,
                "phase_name": phase_name,
                "phase_started_at": started_at,
                "updated_at": now,
                "done": done,
            }
            if scenes_done is not None:
                progress["scenes_done"] = scenes_done
            if total_scenes is not None:
                progress["total_scenes"] = total_scenes

            state["progress"] = progress
            ct.pipeline_state = state
            db.commit()
    except Exception:
        logger.warning("[progress] 스탬프 저장 실패 post_id=%d phase=%d", post_id, phase, exc_info=True)


def clear_checkpoint_keep_progress(post_id: int) -> None:
    """Phase 7 완료 후 체크포인트 키만 제거, progress 보존."""
    try:
        from db.session import SessionLocal
        from db.models import Content

        with SessionLocal() as db:
            ct = db.query(Content).filter_by(post_id=post_id).first()
            if ct is None or ct.pipeline_state is None:
                return
            state = dict(ct.pipeline_state)
            for key in _CHECKPOINT_KEYS:
                state.pop(key, None)
            ct.pipeline_state = state if state else None
            db.commit()
    except Exception:
        logger.warning("[progress] 체크포인트 클리어 실패 post_id=%d", post_id, exc_info=True)
