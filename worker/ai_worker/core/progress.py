"""Pipeline runtime state helpers, stored independently from Content business data."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from ai_worker.core.runtime_state import delete_runtime_state, get_runtime_state, put_runtime_state

logger = logging.getLogger(__name__)


def stamp_progress(
    post_id: int,
    phase: int,
    phase_name: str,
    *,
    scenes_done: int | None = None,
    total_scenes: int | None = None,
    done: bool = False,
) -> None:
    """Atomically replace only the progress namespace (no contents JSON RMW)."""
    now = datetime.now(timezone.utc).isoformat()
    previous = get_runtime_state(post_id, "progress") or {}
    started_at = previous.get("phase_started_at", now) if previous.get("current_phase") == phase else now
    progress: dict[str, Any] = {
        "current_phase": phase,
        "phase_name": phase_name,
        "phase_started_at": started_at,
        "updated_at": now,
        "last_heartbeat_at": now,
        "done": done,
    }
    if scenes_done is not None:
        progress["scenes_done"] = scenes_done
    if total_scenes is not None:
        progress["total_scenes"] = total_scenes
    put_runtime_state(post_id, "progress", progress)


def load_render_checkpoint(post_id: int) -> dict[str, Any] | None:
    """Return new checkpoint state, then legacy state during the rolling upgrade."""
    state = get_runtime_state(post_id, "render_checkpoint")
    if state is not None:
        return state
    try:
        from db.session import SessionLocal
        from db.models import Content
        with SessionLocal() as db:
            content = db.query(Content).filter_by(post_id=post_id).first()
            return dict(content.pipeline_state or {}) if content else None
    except Exception:
        logger.warning("[progress] legacy checkpoint read failed post_id=%d", post_id, exc_info=True)
        return None


def save_render_checkpoint(post_id: int, checkpoint: dict[str, Any]) -> None:
    put_runtime_state(post_id, "render_checkpoint", checkpoint)


def clear_checkpoint_keep_progress(post_id: int) -> None:
    """Remove only the completed render checkpoint; leave progress and diagnostics intact."""
    delete_runtime_state(post_id, "render_checkpoint")


def mark_degraded(post_id: int, reason: str) -> None:
    """Persist a non-terminal SLA downgrade independently from progress/checkpoints."""
    now = datetime.now(timezone.utc).isoformat()
    previous = get_runtime_state(post_id, "sla") or {}
    reasons = list(previous.get("degrade_reasons") or [])
    if reason not in reasons:
        reasons.append(reason)
    put_runtime_state(post_id, "sla", {
        "degraded": True,
        "degrade_reasons": reasons,
        "deadline_breached_at": previous.get("deadline_breached_at", now),
    })


def save_generation_diagnostics(post_id: int, diagnostics: dict[str, Any]) -> None:
    """Persist sanitised quality facts only; never save prompts or raw LLM output."""
    put_runtime_state(post_id, "generation_diagnostics", diagnostics)


def save_failure(post_id: int, *, code: str, stage: str, retryable: bool, error_summary: str) -> None:
    """Store failure details with normalized stage name.

    Args:
        post_id: Post ID
        code: Failure code (e.g., RENDER_FFMPEG_ERROR)
        stage: Phase name in Korean (e.g., '씬 구성') — will be normalized to WAGGLE:xxx
        retryable: Whether retry is possible
        error_summary: Error message (max 500 chars)
    """
    normalized_stage = normalize_failure_stage(stage)
    put_runtime_state(post_id, "failure", {
        "failure_code": code,
        "failure_stage": normalized_stage,
        "retryable": retryable,
        "error_summary": error_summary[:500],
    })


def normalize_failure_stage(korean_name: str) -> str:
    """Map Korean phase name to WAGGLE:xxx constant.

    Mapping table based on current pipeline phases.
    If a new phase is discovered, add it to PHASE_MAPPING.
    """
    # Phase name to WAGGLE:xxx mapping (Korean → English constant)
    # From ai_worker/core/processor.py stamp_progress() calls:
    PHASE_MAPPING = {
        # Video rendering pipeline (processor.py)
        "자원 분석": "WAGGLE:RESOURCE_ANALYSIS",
        "대본 생성": "WAGGLE:SCRIPT_GENERATION",
        "씬 구성": "WAGGLE:SCENE_COMPOSE",
        "비디오 프롬프트": "WAGGLE:VIDEO_PROMPT",
        "비디오 클립": "WAGGLE:VIDEO_CLIP",
        "FFmpeg 렌더링": "WAGGLE:FFMPEG_RENDER",
        "TTS 합성": "WAGGLE:TTS_SYNTHESIS",
        # Generic stages (fallback for main.py errors)
        "tts": "WAGGLE:TTS",
        "llm": "WAGGLE:LLM",
        "render": "WAGGLE:RENDER",
        "ffmpeg_render": "WAGGLE:FFMPEG_RENDER",
        "runtime_state": "WAGGLE:RUNTIME_STATE",
    }

    if korean_name in PHASE_MAPPING:
        return PHASE_MAPPING[korean_name]

    # Fallback for unmapped phases: use WAGGLE:PHASE_<name> format
    if korean_name.isdigit():
        return f"WAGGLE:PHASE_{korean_name}"

    # Generic fallback for any other unknown phase
    return "WAGGLE:PHASE_UNKNOWN"
