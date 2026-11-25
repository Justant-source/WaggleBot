"""PROCESSING 고착 회수 — 워커 크래시·컨테이너 재시작·DB 끊김으로 남은 항목을 풀어준다.

활동 기준(last_activity): content_runtime_state(progress).last_heartbeat_at 과
posts.updated_at 중 더 최근 값. 둘 다 UTC(naive는 UTC로 간주)이며 미래 값은 '활동 중'으로 본다.
현재 프로세스가 처리 중인 항목(exclude_ids)은 회수하지 않는다.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Callable, Iterable

from sqlalchemy.orm import Session

from config.settings import MAX_RETRY_COUNT, STALE_PROCESSING_MINUTES
from db.models import Post, PostStatus
from db.session import SessionLocal

logger = logging.getLogger(__name__)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _parse_iso(raw: object) -> datetime | None:
    if not isinstance(raw, str) or not raw:
        return None
    try:
        return _as_utc(datetime.fromisoformat(raw.replace("Z", "+00:00")))
    except ValueError:
        return None


def load_heartbeat(post_id: int) -> datetime | None:
    """progress.last_heartbeat_at (없으면 updated_at) → aware UTC. 읽기 실패 시 None."""
    from ai_worker.core.runtime_state import get_runtime_state

    state = get_runtime_state(post_id, "progress") or {}
    return _parse_iso(state.get("last_heartbeat_at")) or _parse_iso(state.get("updated_at"))


def reclaim_stuck_posts(
    *,
    startup: bool = False,
    stale_minutes: int | None = None,
    exclude_ids: Iterable[int] = (),
    now: datetime | None = None,
    session_factory: Callable[[], Session] = SessionLocal,
    heartbeat_loader: Callable[[int], datetime | None] = load_heartbeat,
    max_retry: int = MAX_RETRY_COUNT,
) -> dict[str, list[int]]:
    """고착 PROCESSING을 APPROVED(재시도 여유) 또는 FAILED(재시도 소진)로 되돌린다.

    startup=True 이면 활동 시각과 무관하게 전부 회수한다(이전 프로세스는 이미 죽었음).
    Returns {"requeued": [...], "failed": [...]}.
    """
    threshold = timedelta(minutes=STALE_PROCESSING_MINUTES if stale_minutes is None else stale_minutes)
    now = _as_utc(now) or datetime.now(timezone.utc)
    excluded = set(exclude_ids)
    out: dict[str, list[int]] = {"requeued": [], "failed": []}

    with session_factory() as session:
        rows = session.query(Post.id, Post.retry_count, Post.updated_at).filter(
            Post.status == PostStatus.PROCESSING
        ).all()
        for post_id, retry_count, updated_at in rows:
            if post_id in excluded:
                continue
            if not startup:
                beats = [t for t in (_as_utc(updated_at), heartbeat_loader(post_id)) if t is not None]
                last = max(beats) if beats else None
                if last is not None and now - last < threshold:
                    continue
                idle = f"{int((now - last).total_seconds() // 60)}분" if last else "알 수 없음"
            else:
                idle = "워커 재시작"
            exhausted = (retry_count or 0) >= max_retry
            new_status = PostStatus.FAILED if exhausted else PostStatus.APPROVED
            note = (
                f"PROCESSING 고착 회수({idle} 무활동)"
                + (f": 재시도 {retry_count}/{max_retry} 소진 → FAILED" if exhausted else " → APPROVED 재큐")
            )
            # status 조건부 UPDATE: 그 사이 정상 전이된 행은 건드리지 않는다.
            changed = (
                session.query(Post)
                .filter(Post.id == post_id, Post.status == PostStatus.PROCESSING)
                .update(
                    {Post.status: new_status, Post.last_error: note[:1000]},
                    synchronize_session=False,
                )
            )
            if not changed:
                continue
            out["failed" if exhausted else "requeued"].append(post_id)
            logger.warning("🔄 고착 포스트 회수: post_id=%d → %s | %s", post_id, new_status.value, note)
        session.commit()

    for post_id in out["failed"]:
        try:
            from ai_worker.core.progress import save_failure

            save_failure(post_id, code="INFRA_STUCK_PROCESSING", stage="runtime_state",
                         retryable=True, error_summary="PROCESSING 고착 회수 후 재시도 소진")
        except Exception:
            logger.warning("고착 실패 상세 저장 실패: post_id=%d", post_id, exc_info=True)
    return out
