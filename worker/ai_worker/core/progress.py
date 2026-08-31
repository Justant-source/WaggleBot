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
    put_runtime_state(post_id, "failure", {
        "failure_code": code,
        "failure_stage": stage,
        "retryable": retryable,
        "error_summary": error_summary[:500],
    })
