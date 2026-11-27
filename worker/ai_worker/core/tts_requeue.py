"""TTS 서버 장애 재큐의 연속 횟수·백오프 상태 (스키마 변경 없이 posts.last_error에 보관).

배경: TTSUnavailable은 FAILED 대신 APPROVED 재큐(retry_count 유지)로 처리한다. 하지만 서버가 특정 글에만
계속 500/429/대기초과를 내면 같은 글이 30초마다 재선택돼 뒤 글이 영원히 막힌다. 그래서 연속 재큐 횟수를
세고(상한 TTS_REQUEUE_MAX) 증가하는 대기 시간(백오프) 동안은 그 글을 다시 집지 않는다.

저장 위치: ``posts.last_error`` 선두의 마커 ``[tts_requeue n=<횟수> at=<epoch초>]``.
 - 별도 컬럼/마이그레이션 불필요, 워커 재시작에도 유지된다(메모리 dict는 재시작 시 상한이 리셋됨).
 - llm_tts_stage가 시작 시 last_error를 비우므로 ``carry_marker``로 마커만 이어받는다.
 - 마지막 재큐로부터 ``STATE_TTL_SEC``(기본 1시간)이 지나면 만료 → 횟수 0(수동 재승인·장기 방치 보호).
"""
from __future__ import annotations

import re
import time

from config import settings as _cfg

_MARKER_RE = re.compile(r"^\[tts_requeue n=(\d+) at=(\d+)\]")
STATE_TTL_SEC = 3600.0


def parse_state(last_error: str | None, now: float | None = None) -> tuple[int, float]:
    """(연속 재큐 횟수, 마지막 재큐 시각 epoch). 마커 없음/만료면 (0, 0.0)."""
    m = _MARKER_RE.match((last_error or "").lstrip())
    if not m:
        return 0, 0.0
    count, at = int(m.group(1)), float(m.group(2))
    now = time.time() if now is None else now
    if now - at > STATE_TTL_SEC:
        return 0, 0.0
    return count, at


def backoff_sec(count: int) -> float:
    """count회째 재큐 뒤 다음 시도까지 대기: base·2^(count-1), 상한 max (30, 60, 120, 240 … ≤600)."""
    if count <= 0:
        return 0.0
    base = float(_cfg.TTS_REQUEUE_BACKOFF_BASE_SEC)
    cap = float(_cfg.TTS_REQUEUE_BACKOFF_MAX_SEC)
    return min(cap, base * (2 ** (count - 1)))


def is_eligible(last_error: str | None, now: float | None = None) -> bool:
    """백오프가 지났거나 재큐 이력이 없으면 True(다시 집어도 됨)."""
    now = time.time() if now is None else now
    count, at = parse_state(last_error, now)
    return count == 0 or now >= at + backoff_sec(count)


def next_count(last_error: str | None, now: float | None = None) -> int:
    """이번 재큐를 포함한 연속 횟수."""
    return parse_state(last_error, now)[0] + 1


def max_requeues() -> int:
    return max(1, int(_cfg.TTS_REQUEUE_MAX))


def is_exhausted(count: int) -> bool:
    return count >= max_requeues()


def format_note(count: int, reason: str, now: float | None = None) -> str:
    """재큐 시 last_error에 쓰는 문자열(마커 선두, 1000자 제한은 호출부)."""
    now = int(time.time() if now is None else now)
    return (
        f"[tts_requeue n={count} at={now}] {reason} → APPROVED 재큐 "
        f"{count}/{max_requeues()}회, 다음 시도 ≥{int(backoff_sec(count))}초 후"
    )


def carry_marker(last_error: str | None) -> str | None:
    """llm_tts_stage 시작 시 last_error를 비우되 재큐 마커만 보존한다(만료 판정은 읽을 때)."""
    m = _MARKER_RE.match((last_error or "").lstrip())
    return m.group(0) if m else None
