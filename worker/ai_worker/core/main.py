"""AI Worker 메인 루프 — 파이프라인 병렬 처리.

구조:
  _llm_tts_worker  : APPROVED 폴링 → LLM+TTS (CUDA) → render_queue에 적재
  _render_worker   : render_queue 소비 → 렌더링 (Phase 7 LTX-2 + CPU) → PREVIEW_RENDERED

두 워커가 asyncio.gather로 동시 실행되지만, _gpu_stage_lock으로
GPU 작업(LLM+TTS vs Phase 7 LTX-2)을 직렬화하여 VRAM 충돌을 방지한다.
LLM+TTS 단계는 외부 Local-TTS 서버에 합성을 맡기며, 서버 장애는 FAILED가 아닌 hold/재큐로 처리한다.
"""
import asyncio
import logging
import signal
from datetime import datetime, timezone
from sqlalchemy import case

from ai_worker.core.shutdown import get_shutdown_event, is_shutting_down, request_shutdown
from ai_worker.tts.synth import TTSUnavailable, wait_for_tts_server
from config.settings import (
    AI_POLL_INTERVAL, CUDA_CONCURRENCY,
    HEARTBEAT_INTERVAL_SEC, PHASE_STALL_SEC, STALE_SCAN_INTERVAL_SEC,
)
from db.models import Post, Content, PostStatus
from db.session import SessionLocal, init_db

logger = logging.getLogger(__name__)


def _classify_failure(error: str) -> tuple[str, str, bool]:
    """Classify failure into (code, stage, retryable).

    Returns:
        (failure_code, failure_stage, retryable)

    Failure codes:
      - INFRA_DB_CONFLICT: Database concurrency conflict (retry-able)
      - INFRA_DB_DISCONNECT: MySQL connection lost / server has gone away (retry-able)
      - INFRA_TIMEOUT: Phase timeout (retry-able)
      - INFRA_OOM: Out of memory (retry-able)
      - INFRA_GPU_UNAVAILABLE: GPU not available (retry-able)
      - RENDER_FFMPEG_ERROR: FFmpeg encoding failed (retry-able)
      - RENDER_ASSET_MISSING: Input asset missing (not retry-able)
      - RENDER_INVALID_INPUT: Invalid input data (not retry-able)
      - RENDER_UNKNOWN: Unclassified render error (retry-able)
      - TTS_GENERATION_FAILED: TTS synthesis failed (retry-able)
      - VARIANT_LLM_ERROR: LLM content refusal (not retry-able)
    """
    lower = error.lower()
    prefix = (error or "").strip().split(":", 1)[0].strip().upper()
    if prefix.startswith(("SIBOM_", "DURATION_", "VARIANT_", "LAYOUT_")) or prefix.startswith("SCRIPT_"):
        return prefix, "QUALITY_GATE", False

    # Infrastructure errors (retryable)
    if "record has changed since last read" in lower or "(1020)" in lower:
        return "INFRA_DB_CONFLICT", "runtime_state", True
    if ("server has gone away" in lower or "lost connection to" in lower
            or "(2006" in lower or "(2013" in lower):
        return "INFRA_DB_DISCONNECT", "runtime_state", True
    if "timeout" in lower or "timed out" in lower:
        return "INFRA_TIMEOUT", "render", True
    if "out of memory" in lower or "oom" in lower or ("cuda" in lower and "memory" in lower):
        return "INFRA_OOM", "render", True
    if "gpu" in lower and ("unavailable" in lower or "not found" in lower):
        return "INFRA_GPU_UNAVAILABLE", "render", True

    # Render errors
    if "ffmpeg" in lower:
        if "not found" in lower or "missing" in lower:
            return "RENDER_ASSET_MISSING", "ffmpeg_render", False
        return "RENDER_FFMPEG_ERROR", "ffmpeg_render", True

    # Audio/TTS errors (retryable — may recover with retry)
    if "tts" in lower or "audio" in lower:
        if "not found" in lower or "missing" in lower:
            return "RENDER_ASSET_MISSING", "tts", False
        return "TTS_GENERATION_FAILED", "tts", True

    # LLM errors (non-retryable for refusals, retryable for API errors)
    if "llm" in lower or "claude" in lower:
        if "refused" in lower or "refuse" in lower or "content policy" in lower:
            return "VARIANT_LLM_ERROR", "llm", False
        # LLM API error — could be transient
        return "RENDER_UNKNOWN", "llm", True

    # Asset errors
    if "not found" in lower or "missing" in lower or "filenotfound" in lower:
        return "RENDER_ASSET_MISSING", "render", False
    if "invalid" in lower or "malformed" in lower:
        return "RENDER_INVALID_INPUT", "render", False

    # Default: unknown but retryable
    return "RENDER_UNKNOWN", "render", True


def _mark_post_failed(post_id: int, error: str = "") -> None:
    """예외 발생 시 post를 FAILED로 안전하게 마킹하고 last_error를 기록한다."""
    try:
        with SessionLocal() as session:
            post = session.query(Post).filter_by(id=post_id).first()
            if post is not None and post.status not in (
                PostStatus.PREVIEW_RENDERED, PostStatus.RENDERED, PostStatus.UPLOADED
            ):
                post.status = PostStatus.FAILED
                post.last_error = error[:1000] if error else None
                session.commit()

                code, stage, retryable = _classify_failure(error or "")
                from ai_worker.core.progress import save_failure
                save_failure(post_id, code=code, stage=stage, retryable=retryable, error_summary=error or "pipeline failed")
    except Exception:
        logger.exception("FAILED 마킹 실패: post_id=%d", post_id)


def _mark_post_declined(post_id: int, reason: str = "") -> None:
    """LLM 콘텐츠 거부 시 post를 DECLINED로 마킹한다 (재시도 불필요)."""
    try:
        with SessionLocal() as session:
            post = session.query(Post).filter_by(id=post_id).first()
            if post is not None:
                post.status = PostStatus.DECLINED
                post.last_error = reason[:1000] if reason else None
                session.commit()
                logger.warning("콘텐츠 거부로 DECLINED 처리: post_id=%d | %s", post_id, reason)
    except Exception:
        logger.exception("DECLINED 마킹 실패: post_id=%d", post_id)


def _recover_stuck_posts() -> None:
    """시작 시 PROCESSING 고착 포스트를 회수한다 (재시도 소진 시 FAILED, 아니면 APPROVED)."""
    from ai_worker.core.recovery import reclaim_stuck_posts

    result = reclaim_stuck_posts(startup=True)
    if result["requeued"] or result["failed"]:
        logger.info("✅ 시작 시 고착 회수: APPROVED %d건, FAILED %d건",
                    len(result["requeued"]), len(result["failed"]))


# 이 프로세스가 현재 소유(LLM+TTS → 렌더 큐 → 렌더)한 PROCESSING post id.
# 하트비트 대상이자 주기적 고착 회수의 제외 대상. 단일 이벤트 루프 스레드에서만 변경한다.
_inflight_post_ids: set[int] = set()


_stall_warned: set[int] = set()


async def _heartbeat_loop() -> None:
    """소유 중인 post의 progress 하트비트를 주기 갱신 (큐/락 대기·렌더 중에도 '살아있음' 표시).

    같은 phase에서 진행 표시(stamp)가 PHASE_STALL_SEC 넘게 없으면 갱신을 멈추고 경고만 남긴다
    (코루틴 취소·상태 변경은 하지 않는다 — 소유 프로세스가 아직 실행 중일 수 있음).
    """
    from ai_worker.core.progress import touch_heartbeat_unless_stalled

    shutdown_event = get_shutdown_event()
    loop = asyncio.get_running_loop()
    while not is_shutting_down():
        live = set(_inflight_post_ids)
        _stall_warned.intersection_update(live)
        for pid in list(live):
            try:
                outcome = await loop.run_in_executor(None, touch_heartbeat_unless_stalled, pid, PHASE_STALL_SEC)
            except Exception:
                logger.warning("하트비트 갱신 실패: post_id=%d", pid, exc_info=True)
                continue
            if outcome == "stalled":
                if pid not in _stall_warned:
                    _stall_warned.add(pid)
                    logger.warning(
                        "⚠️ 단계 정체: post_id=%d — 진행 표시가 %.0f초 넘게 없어 하트비트 갱신 중단 "
                        "(처리 코루틴은 취소하지 않음)", pid, PHASE_STALL_SEC,
                    )
            else:
                _stall_warned.discard(pid)
        try:
            await asyncio.wait_for(shutdown_event.wait(), timeout=HEARTBEAT_INTERVAL_SEC)
        except asyncio.TimeoutError:
            pass


async def _stale_reclaim_loop() -> None:
    """소유자 없이 오래 방치된 PROCESSING(DB 끊김으로 FAILED 마킹 실패 등)을 주기적으로 회수."""
    from ai_worker.core.recovery import reclaim_stuck_posts

    shutdown_event = get_shutdown_event()
    loop = asyncio.get_running_loop()
    while not is_shutting_down():
        try:
            await asyncio.wait_for(shutdown_event.wait(), timeout=STALE_SCAN_INTERVAL_SEC)
            break
        except asyncio.TimeoutError:
            pass
        try:
            await loop.run_in_executor(
                None, lambda: reclaim_stuck_posts(exclude_ids=set(_inflight_post_ids))
            )
        except Exception:
            logger.warning("고착 회수 점검 실패 (다음 주기에 재시도)", exc_info=True)


# CUDA 리소스를 직렬화하는 세마포어 (LLM + TTS 는 순차 실행)
_cuda_sem: asyncio.Semaphore | None = None


def _get_cuda_sem() -> asyncio.Semaphore:
    global _cuda_sem
    if _cuda_sem is None:
        _cuda_sem = asyncio.Semaphore(CUDA_CONCURRENCY)
    return _cuda_sem


# GPU 단계 락 — LLM+TTS 단계와 렌더(Phase 7 LTX-2) 직렬화.
# 이 락으로 두 워커의 GPU 작업을 직렬화한다.
_gpu_stage_lock: asyncio.Lock | None = None


def _get_gpu_stage_lock() -> asyncio.Lock:
    global _gpu_stage_lock
    if _gpu_stage_lock is None:
        _gpu_stage_lock = asyncio.Lock()
    return _gpu_stage_lock


# ---------------------------------------------------------------------------
# 파이프라인 워커
# ---------------------------------------------------------------------------

def _post_priority(post: Post) -> int:
    return 0 if post.site_code == "again_spring" else 1


# ---------------------------------------------------------------------------
# TTS 서버 일시 장애 시 보류·재큐
# ---------------------------------------------------------------------------
#
# Local-TTS 서버가 불가하면 포스트를 FAILED로 만들지 않는다.
#  1) 집기 전: 서버 확인이 실패하면 APPROVED 폴링을 보류한다(상태·retry_count 변화 없음).
#  2) 처리 중: synthesize가 TTS_SERVER_MAX_WAIT_SEC 안에 서버를 못 얻어 TTSUnavailable을 던지면
#     PROCESSING → APPROVED로 되돌리고 retry_count를 원복한다(재시도 횟수 소모 없음).
# 합성 대기 상한은 synth 쪽 TTS_SERVER_MAX_WAIT_SEC가 단일 SSOT이며, 여기서는 대기 루프를 두지 않는다.

_TTS_HOLD_RECHECK_SEC = 30.0   # 보류 중 서버 재확인 간격
_TTS_PROBE_TIMEOUT_SEC = 3.0   # 집기 전 비차단 확인 한도
_tts_hold_active: bool = False


async def _tts_hold_check() -> bool:
    """TTS 서버가 불가하면 True(보류). 확인 중 예외는 fail-open(False).

    상태가 바뀔 때만 INFO 로그(반복 로그 폭주 방지).
    """
    global _tts_hold_active
    try:
        ok = await wait_for_tts_server(timeout_sec=_TTS_PROBE_TIMEOUT_SEC)
    except Exception:
        logger.debug("TTS 서버 확인 실패 — 진행(fail-open)", exc_info=True)
        ok = True
    held = not ok
    if held != _tts_hold_active:
        if held:
            logger.info("⏸ TTS 서버 불가 — APPROVED 집기 보류")
        else:
            logger.info("▶ TTS 서버 복구 — APPROVED 처리 재개")
        _tts_hold_active = held
    return held


class _TTSRequeued(Exception):
    """TTS 서버 장애로 retry_count 소모 없이 APPROVED로 되돌렸다."""


def _requeue_without_retry(post_id: int, retry_before: int, note: str) -> bool:
    """PROCESSING → APPROVED, retry_count를 처리 시작 전 값으로 복원 (status 조건부 UPDATE)."""
    with SessionLocal() as session:
        changed = (
            session.query(Post)
            .filter(Post.id == post_id, Post.status == PostStatus.PROCESSING)
            .update(
                {Post.status: PostStatus.APPROVED, Post.retry_count: retry_before, Post.last_error: note[:1000]},
                synchronize_session=False,
            )
        )
        session.commit()
    return bool(changed)


def _get_retry_count(post_id: int) -> int:
    with SessionLocal() as session:
        row = session.query(Post.retry_count).filter(Post.id == post_id).first()
    return int((row[0] if row else 0) or 0)


async def _run_llm_tts_supervised(processor, post_id: int):
    """llm_tts_stage 실행. TTSUnavailable이면 APPROVED로 재큐(retry_count 유지)하고 _TTSRequeued를 던진다."""
    retry_before = _get_retry_count(post_id)
    try:
        return await processor.llm_tts_stage(post_id)
    except TTSUnavailable as exc:
        _requeue_without_retry(
            post_id, retry_before,
            f"TTS 서버 불가({exc}) → APPROVED 재큐(재시도 횟수 유지)",
        )
        logger.warning("↩ TTS 서버 불가 — APPROVED 재큐(retry_count 유지=%d): post_id=%d | %s",
                       retry_before, post_id, exc)
        raise _TTSRequeued(str(exc)) from exc


async def _llm_tts_worker(render_queue: asyncio.PriorityQueue) -> None:
    """APPROVED 게시글을 폴링해 LLM+TTS 처리 후 render_queue에 적재."""
    from ai_worker.core.processor import RobustProcessor
    processor = RobustProcessor()
    cuda_sem = _get_cuda_sem()
    gpu_lock = _get_gpu_stage_lock()
    shutdown_event = get_shutdown_event()

    while not is_shutting_down():
        post_id: int | None = None
        post_site: str | None = None
        try:
            with SessionLocal() as session:
                post = (
                    session.query(Post)
                    .filter(Post.status == PostStatus.APPROVED)
                    .order_by(case((Post.site_code == "again_spring", 0), else_=1), Post.created_at.asc())
                    .first()
                )
                if post is not None:
                    post_id = post.id
                    post_site = post.site_code
        except Exception:
            # DB 끊김 등 일시 오류로 워커 태스크 전체가 죽지 않게 한다 (프로세스 종료 → 재시작 루프 방지).
            logger.warning("APPROVED 폴링 실패 — 다음 주기에 재시도", exc_info=True)
            try:
                await asyncio.wait_for(shutdown_event.wait(), timeout=max(AI_POLL_INTERVAL, 5))
            except asyncio.TimeoutError:
                pass
            continue

        if post_id is None:
            # 셧다운 이벤트 또는 폴링 타임아웃 대기
            try:
                await asyncio.wait_for(
                    shutdown_event.wait(), timeout=AI_POLL_INTERVAL
                )
            except asyncio.TimeoutError:
                pass
            continue

        # TTS 서버가 불가하면 post를 집지 않는다(PROCESSING·gpu_lock·retry_count 보존).
        # 확인 예외는 fail-open → 기존대로 진행.
        if await _tts_hold_check():
            try:
                await asyncio.wait_for(
                    shutdown_event.wait(), timeout=max(AI_POLL_INTERVAL, _TTS_HOLD_RECHECK_SEC),
                )
            except asyncio.TimeoutError:
                pass
            continue

        # GPU 작업: LLM + TTS (gpu_lock으로 렌더 Phase 7과 직렬화)
        result = None
        requeued_hold = False
        _inflight_post_ids.add(post_id)
        if gpu_lock.locked():
            logger.info(
                "⏳ GPU 사용 중 (렌더링/비디오 생성) — LLM+TTS 대기: post_id=%d", post_id
            )
        async with gpu_lock:
            async with cuda_sem:
                try:
                    script, audio_path = await _run_llm_tts_supervised(processor, post_id)
                    result = (post_id, script, audio_path)
                except _TTSRequeued:
                    _inflight_post_ids.discard(post_id)
                    requeued_hold = True
                except Exception as exc:
                    from ai_worker.llm.transport import LLMContentRefusalError
                    if isinstance(exc, LLMContentRefusalError):
                        logger.warning("LLM 콘텐츠 거부: post_id=%d | %s", post_id, exc)
                        _mark_post_declined(post_id, reason=str(exc))
                        _inflight_post_ids.discard(post_id)
                    else:
                        logger.exception("LLM+TTS 실패: post_id=%d", post_id)
                        _mark_post_failed(post_id, error=repr(exc))
                        _inflight_post_ids.discard(post_id)
                    await asyncio.sleep(5)

        if requeued_hold:
            # 재큐 직후 곧바로 다시 집어 LLM 단계를 반복하지 않도록 서버 복구를 기다린다.
            try:
                await asyncio.wait_for(shutdown_event.wait(), timeout=_TTS_HOLD_RECHECK_SEC)
            except asyncio.TimeoutError:
                pass
            continue

        # gpu_lock 해제 후 큐 적재 (데드락 방지: 큐 만석 시 render_worker가 lock 필요)
        if result is not None:
            await render_queue.put((0 if post_site == "again_spring" else 1, datetime.now(timezone.utc).timestamp(), *result))
            logger.info("LLM+TTS 완료, 렌더 큐 적재: post_id=%d (큐 크기=%d)",
                        post_id, render_queue.qsize())

    logger.info("🛑 _llm_tts_worker 종료")


async def _render_worker(render_queue: asyncio.PriorityQueue) -> None:
    """render_queue에서 꺼내 렌더링 (h264_nvenc GPU 인코딩).

    Phase 7(LTX-2 비디오 생성) 포함 시 gpu_lock으로 LLM+TTS와 직렬화.
    """
    from ai_worker.core.processor import RobustProcessor
    processor = RobustProcessor()
    gpu_lock = _get_gpu_stage_lock()

    while True:
        try:
            _priority, _queued_at, post_id, script, audio_path = await asyncio.wait_for(
                render_queue.get(), timeout=2.0
            )
        except asyncio.TimeoutError:
            if is_shutting_down() and render_queue.empty():
                break
            continue

        try:
            if gpu_lock.locked():
                logger.info(
                    "⏳ GPU 사용 중 (LLM+TTS) — 렌더링 대기: post_id=%d", post_id
                )
            async with gpu_lock:
                # render_stage는 동기 작업 — executor 사용. Phase 7 LTX-2 포함.
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(
                    None, processor.render_stage, post_id, script, audio_path
                )
        except TTSUnavailable as exc:
            # 렌더 중 댓글/outro TTS 폴백이 서버 장애로 실패 — FAILED 대신 APPROVED 재큐(재시도 횟수 유지).
            logger.warning("렌더 중 TTS 서버 불가 — APPROVED 재큐: post_id=%d | %s", post_id, exc)
            _requeue_without_retry(
                post_id, _get_retry_count(post_id),
                f"렌더 중 TTS 서버 불가({exc}) → APPROVED 재큐",
            )
        except Exception as exc:
            logger.exception("렌더링 실패: post_id=%d", post_id)
            _mark_post_failed(post_id, error=repr(exc))
        finally:
            _inflight_post_ids.discard(post_id)
            render_queue.task_done()

    logger.info("🛑 _render_worker 종료")


# ---------------------------------------------------------------------------
# 업로드 워커 (기존 동작 유지)
# ---------------------------------------------------------------------------

async def upload_once() -> bool:
    """RENDERED 상태 포스트를 찾아 업로드 실행."""
    from config.settings import load_pipeline_config
    from uploaders.uploader import upload_post

    cfg = load_pipeline_config()
    if cfg.get("auto_upload", "false") != "true":
        return False  # 자동 업로드 비활성화 시 건너뜀

    with SessionLocal() as session:
        post = (
            session.query(Post)
            .filter(Post.status == PostStatus.RENDERED)
            .order_by(Post.created_at.asc())
            .first()
        )
        if post is None:
            return False

        content = session.query(Content).filter_by(post_id=post.id).first()
        if content is None:
            logger.error("Content 없음: post_id=%d", post.id)
            return False

        try:
            success = upload_post(post, content, session)
            if success:
                post.status = PostStatus.UPLOADED
                session.commit()
                logger.info("업로드 완료: post_id=%d", post.id)
            else:
                post.status = PostStatus.FAILED
                post.last_error = "업로드 실패"
                session.commit()
                logger.warning("업로드 실패, FAILED 처리: post_id=%d", post.id)
        except Exception:
            logger.exception("업로드 실패: post_id=%d", post.id)
            session.rollback()

    return True


async def _upload_loop() -> None:
    """RENDERED 게시글을 주기적으로 업로드."""
    shutdown_event = get_shutdown_event()

    while not is_shutting_down():
        try:
            found = await upload_once()
        except Exception:
            logger.exception("업로드 루프 예외")
            found = False

        # 셧다운 이벤트 또는 폴링 타임아웃 대기
        try:
            await asyncio.wait_for(
                shutdown_event.wait(),
                timeout=AI_POLL_INTERVAL if not found else 1,
            )
        except asyncio.TimeoutError:
            pass

    logger.info("🛑 _upload_loop 종료")


# ---------------------------------------------------------------------------
# 큐 드레인
# ---------------------------------------------------------------------------

def _drain_render_queue(render_queue: asyncio.PriorityQueue) -> None:
    """미처리 큐 항목의 포스트를 APPROVED로 복원한다."""
    drained = 0
    while not render_queue.empty():
        try:
            _priority, _queued_at, post_id, _script, _audio = render_queue.get_nowait()
            _inflight_post_ids.discard(post_id)
            with SessionLocal() as session:
                post = session.query(Post).filter_by(id=post_id).first()
                if post is not None and post.status == PostStatus.PROCESSING:
                    post.status = PostStatus.APPROVED
                    session.commit()
                    logger.info("🔄 큐 드레인: post_id=%d → APPROVED", post_id)
                    drained += 1
            render_queue.task_done()
        except Exception:
            logger.exception("큐 드레인 중 오류")
            break

    if drained:
        logger.info("✅ 큐 드레인 완료: %d건 복원", drained)


# ---------------------------------------------------------------------------
# 메인
# ---------------------------------------------------------------------------

async def _main_loop() -> None:
    loop = asyncio.get_running_loop()
    shutdown_event = get_shutdown_event()

    # 시그널 핸들러 등록
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, request_shutdown)

    render_queue: asyncio.PriorityQueue = asyncio.PriorityQueue(maxsize=4)

    try:
        await asyncio.gather(
            _llm_tts_worker(render_queue),
            _render_worker(render_queue),
            _upload_loop(),
            _heartbeat_loop(),
            _stale_reclaim_loop(),
        )
    finally:
        logger.info("🛑 메인 루프 종료 — 큐 드레인 시작")
        _drain_render_queue(render_queue)
        logger.info("✅ Graceful shutdown 완료")


async def _startup() -> None:
    """앱 시작 시 외부 서비스 준비 대기."""
    # 비차단 확인: 서버가 없어도 기동은 계속한다(집기 전 hold 로직이 APPROVED 처리를 보류).
    ready = await wait_for_tts_server(timeout_sec=_TTS_PROBE_TIMEOUT_SEC)
    if not ready:
        logger.warning("Local-TTS 서버 미준비 — 복구될 때까지 APPROVED 처리를 보류합니다")


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    init_db()

    # 시작 시 고착된 PROCESSING 포스트 복구
    _recover_stuck_posts()

    logger.info("AI Worker 시작 (pipeline 모드, poll_interval=%ds)", AI_POLL_INTERVAL)
    asyncio.run(_startup())
    asyncio.run(_main_loop())


if __name__ == "__main__":
    main()
