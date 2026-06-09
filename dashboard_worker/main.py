"""dashboard_worker — jobs 테이블 폴링 데몬.

Java backend가 enqueue한 Job을 PENDING→RUNNING→DONE/ERROR 으로 처리.
"""
from __future__ import annotations

import gc
import logging
import signal
import sys
import time
from datetime import datetime, timezone

from sqlalchemy import select, update

logger = logging.getLogger(__name__)

POLL_INTERVAL = 3  # seconds

_shutdown = False


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _setup_signals() -> None:
    def handler(sig, frame):
        global _shutdown
        logger.info("dashboard_worker 종료 신호 수신 (sig=%s)", sig)
        _shutdown = True

    signal.signal(signal.SIGTERM, handler)
    signal.signal(signal.SIGINT, handler)


def _claim_pending_job():
    """PENDING Job 하나를 RUNNING으로 원자적 변경 후 반환."""
    from db.session import SessionLocal
    from db.models import Job, JobStatus

    with SessionLocal() as db:
        job = db.execute(
            select(Job)
            .where(Job.status == JobStatus.PENDING)
            .order_by(Job.created_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        ).scalar_one_or_none()
        if job is None:
            return None
        job.status = JobStatus.RUNNING
        job.updated_at = _utcnow()
        db.commit()
        db.refresh(job)
        return job


def _mark_done(job_id: int, result: dict) -> None:
    from db.session import SessionLocal
    from db.models import Job, JobStatus

    with SessionLocal() as db:
        db.execute(
            update(Job).where(Job.id == job_id).values(
                status=JobStatus.DONE,
                result=result,
                updated_at=_utcnow(),
            )
        )
        db.commit()


def _mark_error(job_id: int, error: Exception) -> None:
    from db.session import SessionLocal
    from db.models import Job, JobStatus

    with SessionLocal() as db:
        db.execute(
            update(Job).where(Job.id == job_id).values(
                status=JobStatus.ERROR,
                error=str(error)[:2000],
                updated_at=_utcnow(),
            )
        )
        db.commit()


def run() -> None:
    _setup_signals()
    logger.info("dashboard_worker 시작")

    from dashboard_worker.handlers import HANDLERS

    while not _shutdown:
        job = None
        try:
            job = _claim_pending_job()
            if job is None:
                time.sleep(POLL_INTERVAL)
                continue

            logger.info(
                "잡 처리 시작: %s (id=%s, post_id=%s)",
                job.job_type, job.id, job.post_id,
            )
            handler = HANDLERS.get(job.job_type)
            if handler is None:
                raise ValueError(f"Unknown job_type: {job.job_type}")

            result = handler(job)
            _mark_done(job.id, result or {})
            logger.info("잡 완료: %s (id=%s)", job.job_type, job.id)

        except Exception as exc:
            logger.exception("잡 처리 오류: %s", exc)
            if job is not None:
                try:
                    _mark_error(job.id, exc)
                except Exception:
                    logger.exception("오류 마킹 실패")
        finally:
            gc.collect()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    run()
