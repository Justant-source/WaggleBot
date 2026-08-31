"""Independent, atomic runtime-state storage for long-running content jobs."""
from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from sqlalchemy import text

logger = logging.getLogger(__name__)


def _content_id(db: Any, post_id: int) -> int | None:
    row = db.execute(
        text("SELECT id FROM contents WHERE post_id = :post_id"), {"post_id": post_id}
    ).first()
    return int(row[0]) if row else None


def put_runtime_state(post_id: int, state_key: str, value: Mapping[str, Any]) -> bool:
    """Atomically replace one state namespace without reading another namespace."""
    try:
        from db.session import SessionLocal

        with SessionLocal() as db:
            content_id = _content_id(db, post_id)
            if content_id is None:
                logger.warning("[runtime-state] content missing post_id=%d key=%s", post_id, state_key)
                return False
            db.execute(
                text("""
                    INSERT INTO content_runtime_state (content_id, state_key, state_value)
                    VALUES (:content_id, :state_key, :state_value)
                    ON DUPLICATE KEY UPDATE state_value = VALUES(state_value),
                        updated_at = CURRENT_TIMESTAMP(6)
                """),
                {"content_id": content_id, "state_key": state_key, "state_value": __import__("json").dumps(dict(value), ensure_ascii=False)},
            )
            db.commit()
            return True
    except Exception:
        logger.warning("[runtime-state] upsert failed post_id=%d key=%s", post_id, state_key, exc_info=True)
        return False


def get_runtime_state(post_id: int, state_key: str) -> dict[str, Any] | None:
    """Read a namespaced state value; caller may use legacy fallback if None."""
    try:
        from db.session import SessionLocal

        with SessionLocal() as db:
            row = db.execute(text("""
                SELECT rs.state_value FROM content_runtime_state rs
                JOIN contents c ON c.id = rs.content_id
                WHERE c.post_id = :post_id AND rs.state_key = :state_key
            """), {"post_id": post_id, "state_key": state_key}).first()
            if row is None or row[0] is None:
                return None
            raw = row[0]
            return raw if isinstance(raw, dict) else __import__("json").loads(raw)
    except Exception:
        logger.warning("[runtime-state] read failed post_id=%d key=%s", post_id, state_key, exc_info=True)
        return None


def delete_runtime_state(post_id: int, state_key: str) -> bool:
    try:
        from db.session import SessionLocal

        with SessionLocal() as db:
            db.execute(text("""
                DELETE rs FROM content_runtime_state rs
                JOIN contents c ON c.id = rs.content_id
                WHERE c.post_id = :post_id AND rs.state_key = :state_key
            """), {"post_id": post_id, "state_key": state_key})
            db.commit()
            return True
    except Exception:
        logger.warning("[runtime-state] delete failed post_id=%d key=%s", post_id, state_key, exc_info=True)
        return False
