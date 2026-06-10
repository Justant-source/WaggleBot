"""통합 마이그레이션 러너.

적용되지 않은 SQL 마이그레이션을 순차적으로 실행한다.
schema_migrations 테이블로 적용 이력을 추적한다.

사용법:
    docker compose exec dashboard python -m db.migrations.runner
"""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from sqlalchemy import text
from db.session import engine

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(message)s")

MIGRATIONS_DIR = Path(__file__).parent


def _ensure_tracking_table(conn) -> None:
    """마이그레이션 추적 테이블이 없으면 생성한다."""
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version   VARCHAR(64)  PRIMARY KEY,
            applied_at DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """))
    conn.commit()


def _get_applied(conn) -> set[str]:
    """이미 적용된 마이그레이션 버전 목록을 반환한다."""
    rows = conn.execute(text("SELECT version FROM schema_migrations")).fetchall()
    return {row[0] for row in rows}


def _run_sql(conn, sql_text: str) -> None:
    """세미콜론으로 분리된 SQL 문을 순차 실행한다."""
    for stmt in sql_text.split(";"):
        lines = [
            ln for ln in stmt.splitlines()
            if ln.strip() and not ln.strip().startswith("--")
        ]
        if not lines:
            continue
        conn.execute(text("\n".join(lines)))


def migrate() -> None:
    """미적용 마이그레이션을 순차 실행한다."""
    sql_files = sorted(MIGRATIONS_DIR.glob("*.sql"))

    if not sql_files:
        logger.info("마이그레이션 파일 없음")
        return

    with engine.connect() as conn:
        _ensure_tracking_table(conn)
        applied = _get_applied(conn)

        for sql_file in sql_files:
            version = sql_file.stem  # e.g. "001_images_contents"

            if version in applied:
                logger.info("⏭  %s (이미 적용됨)", version)
                continue

            logger.info("▶  %s 적용 중...", version)
            sql_text = sql_file.read_text(encoding="utf-8")

            try:
                _run_sql(conn, sql_text)
            except Exception as e:
                try:
                    conn.rollback()
                except Exception:
                    pass
                logger.error("❌ %s DDL 실패 (DDL은 이미 자동 커밋됐을 수 있음): %s", version, e)
                raise

            # DDL 성공 — 추적 레코드 삽입 (INSERT IGNORE: 재실행 안전)
            try:
                conn.execute(
                    text("INSERT IGNORE INTO schema_migrations (version) VALUES (:v)"),
                    {"v": version},
                )
                conn.commit()
                logger.info("✅ %s 완료", version)
            except Exception as e:
                conn.rollback()
                logger.error(
                    "❌ %s schema_migrations 기록 실패 — 수동 삽입 필요: "
                    "INSERT INTO schema_migrations (version) VALUES ('%s'): %s",
                    version, version, e,
                )
                raise

    logger.info("마이그레이션 완료")


if __name__ == "__main__":
    migrate()
