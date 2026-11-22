"""Fish Speech 게이트 — Fish가 내려가 있거나 막힌 동안 post를 FAILED로 만들지 않고 대기한다.

Fish(고품질 TTS)는 Flight-Brain GPU 데몬이 수명주기를 관리한다(평소 stop, 필요 시 start,
X-Plane 실행 중에는 올리지 않음). TTS 직전에 Fish health가 실패하면 이 모듈이
``POST FISH_GATE_URL``(Flight-Brain atomic_tts ``/api/gpu/fish/ensure``)로 "올릴 수 있는지"를 묻는다.

응답 ``{state, reason, retry_after_sec}`` 처리:
  - ready                  → Fish health 확인 후 진행
  - starting               → 10초 간격 health 폴링(최대 FISH_GATE_START_MAX_SEC), 실패 시 재질의
  - blocked / unavailable / 호출 실패
                           → FISH_GATE_RECHECK_SEC(기본 30분)마다 재질의하며 대기.
                             대기 중 FISH_GATE_HEARTBEAT_SEC(30초)마다 진행 heartbeat를 갱신하고
                             그 사이 Fish health도 확인한다(누가 올려 두면 즉시 진행).
전체 대기가 FISH_GATE_MAX_WAIT_SEC(기본 24시간)를 넘으면 FishGateTimeout을 던져 기존 FAILED 경로를 따른다.
게이트 서버가 응답하지 않아도(호출 실패) 같은 대기 경로로 health만으로 진행한다.
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from config.settings import (
    FISH_GATE_ENABLED,
    FISH_GATE_HEARTBEAT_SEC,
    FISH_GATE_MAX_WAIT_SEC,
    FISH_GATE_RECHECK_SEC,
    FISH_GATE_START_MAX_SEC,
    FISH_GATE_START_POLL_SEC,
    FISH_GATE_URL,
    FISH_SPEECH_URL,
)

logger = logging.getLogger(__name__)

# 최근 health 성공을 이 시간(초) 동안 재사용해 합성 호출마다 GET이 나가지 않게 한다.
_HEALTH_OK_TTL_SEC = 20.0

_REASON_LABELS = {
    "xplane": "X-Plane 실행 중",
    "video_gen": "영상 생성 중",
    "vram": "VRAM 부족",
    "docker": "Docker 오류",
}


class FishGateTimeout(RuntimeError):
    """FISH_GATE_MAX_WAIT_SEC 안에 Fish를 사용할 수 없었다(기존 FAILED 경로로 이어진다)."""


HealthFn = Callable[[], Awaitable[bool]]
AskFn = Callable[[], Awaitable[dict[str, Any] | None]]
SleepFn = Callable[[float], Awaitable[None]]
ProgressFn = Callable[[int, int, str], None]


async def _default_health() -> bool:
    """wait_for_fish_speech와 같은 방식: GET {FISH_SPEECH_URL}/ 에 HTTP 응답이 오면 살아 있음."""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            await client.get(f"{FISH_SPEECH_URL}/")
        return True
    except Exception:
        return False


async def _default_ask() -> dict[str, Any] | None:
    """게이트 서버에 ensure 요청. 실패(연결·HTTP 오류·잘못된 응답)는 None."""
    if not FISH_GATE_URL:
        return None
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(FISH_GATE_URL, json={"owner": "wagglebot"})
            resp.raise_for_status()
            data = resp.json()
        return data if isinstance(data, dict) else None
    except Exception as exc:
        logger.warning("[fish_gate] 게이트 호출 실패 (%s): %s", FISH_GATE_URL, exc)
        return None


def _default_progress(post_id: int, phase: int, label: str) -> None:
    try:
        from ai_worker.core.progress import stamp_progress
        stamp_progress(post_id, phase, label)
    except Exception:
        logger.debug("[fish_gate] progress 갱신 실패", exc_info=True)


class FishGate:
    """게이트 판정·대기 로직. 의존성은 전부 주입 가능(테스트는 가짜 주입)."""

    def __init__(
        self,
        *,
        health: HealthFn = _default_health,
        ask: AskFn = _default_ask,
        sleep: SleepFn = asyncio.sleep,
        clock: Callable[[], float] = time.monotonic,
        progress: ProgressFn = _default_progress,
        enabled: bool = FISH_GATE_ENABLED,
        recheck_sec: float = FISH_GATE_RECHECK_SEC,
        max_wait_sec: float = FISH_GATE_MAX_WAIT_SEC,
        heartbeat_sec: float = FISH_GATE_HEARTBEAT_SEC,
        start_poll_sec: float = FISH_GATE_START_POLL_SEC,
        start_max_sec: float = FISH_GATE_START_MAX_SEC,
    ) -> None:
        self._health = health
        self._ask = ask
        self._sleep = sleep
        self._clock = clock
        self._progress = progress
        self.enabled = enabled
        self.recheck_sec = recheck_sec
        self.max_wait_sec = max_wait_sec
        self.heartbeat_sec = heartbeat_sec
        self.start_poll_sec = start_poll_sec
        self.start_max_sec = start_max_sec
        self._active: tuple[int, int, str] | None = None  # (post_id, phase, phase_name)
        self._label: str | None = None
        self._health_ok_at: float | None = None

    # ── 현재 post 바인딩 (heartbeat 문구용) ─────────────────────
    def bind_post(self, post_id: int, phase: int, phase_name: str) -> None:
        """TTS를 하는 post를 등록한다. GPU 락으로 한 번에 한 post만 TTS하므로 단일 슬롯이면 충분하다."""
        self._active = (post_id, phase, phase_name)

    def unbind_post(self) -> None:
        self._active = None
        self._label = None

    def wait_label(self, post_id: int) -> str | None:
        """대기 중이면 phase 문구로 쓸 대기 라벨, 아니면 None (processor heartbeat가 덮어쓰지 않도록)."""
        if self._active and self._active[0] == post_id:
            return self._label
        return None

    def _stamp(self, label: str | None) -> None:
        self._label = label
        if self._active is None:
            return
        post_id, phase, phase_name = self._active
        self._progress(post_id, phase, label or phase_name)

    # ── health ───────────────────────────────────────────────
    async def _healthy(self, *, use_cache: bool) -> bool:
        now = self._clock()
        if use_cache and self._health_ok_at is not None and now - self._health_ok_at < _HEALTH_OK_TTL_SEC:
            return True
        ok = await self._health()
        self._health_ok_at = now if ok else None
        return ok

    def invalidate_health(self) -> None:
        self._health_ok_at = None

    # ── 공개 API ─────────────────────────────────────────────
    async def ensure_ready(self, *, why: str = "TTS 직전") -> None:
        """Fish가 쓸 수 있을 때까지 대기한다. 이미 healthy면 즉시 반환(GET 1회, 20초 캐시)."""
        if not self.enabled:
            return
        if await self._healthy(use_cache=True):
            return
        await self._wait(why)

    async def recover(self, why: str) -> bool:
        """요청이 연결 실패/타임아웃으로 끊긴 뒤 호출.

        Fish가 내려가 있어 대기했다가 돌아왔으면 True(호출부가 요청 재시도).
        Fish가 살아 있었으면 False(요청 자체의 문제 → 호출부가 기존 오류 처리).
        """
        if not self.enabled:
            return False
        self.invalidate_health()
        if await self._healthy(use_cache=False):
            return False
        await self._wait(why)
        return True

    async def should_skip_start(self) -> bool:
        """Phase 7 이후 start_fish_speech를 건너뛸지. 게이트가 blocked일 때만 True(실패·미응답이면 기존대로 기동)."""
        if not self.enabled:
            return False
        resp = await self._ask()
        if resp and resp.get("state") == "blocked":
            logger.info(
                "[fish_gate] Fish 기동 건너뜀 — 게이트 blocked (%s)", resp.get("reason"),
            )
            return True
        return False

    # ── 내부 대기 루프 ───────────────────────────────────────
    async def _wait(self, why: str) -> None:
        start = self._clock()
        deadline = start + self.max_wait_sec
        logger.warning("[fish_gate] Fish 사용 불가 — 게이트 확인 시작 (%s)", why)
        try:
            while True:
                if self._clock() >= deadline:
                    raise FishGateTimeout(
                        f"Fish 대기 한도 초과({self.max_wait_sec:.0f}s) — {why}",
                    )
                resp = await self._ask()
                state = (resp or {}).get("state") if resp else None
                reason = (resp or {}).get("reason") if resp else None

                if state in ("ready", "starting"):
                    if await self._poll_until_healthy(deadline, starting=state == "starting"):
                        logger.info("[fish_gate] Fish 준비됨 (%.0fs 대기)", self._clock() - start)
                        return
                    continue  # 기동이 안 끝났으면 다시 묻는다

                label = self._blocked_label(state, reason)
                logger.warning(
                    "[fish_gate] 대기: state=%s reason=%s — %.0f초 후 재확인",
                    state, reason, self.recheck_sec,
                )
                if await self._sleep_checking_health(label, deadline):
                    logger.info("[fish_gate] 대기 중 Fish 가동 확인 (%.0fs 대기)", self._clock() - start)
                    return
        finally:
            self._stamp(None)

    def _blocked_label(self, state: str | None, reason: str | None) -> str:
        minutes = max(int(self.recheck_sec // 60), 1)
        if state == "blocked":
            text = _REASON_LABELS.get(reason or "", reason or "차단됨")
        elif state == "unavailable":
            text = "GPU 데몬 없음"
        else:
            text = "Fish 게이트 응답 없음"
        return f"TTS 대기: {text} — {minutes}분마다 재확인"

    async def _poll_until_healthy(self, deadline: float, *, starting: bool) -> bool:
        """health가 true가 될 때까지 start_poll_sec 간격 폴링(최대 start_max_sec). 성공 여부."""
        limit = min(self._clock() + self.start_max_sec, deadline)
        label = "TTS 대기: Fish 기동 중"
        while True:
            self._stamp(label)
            if await self._healthy(use_cache=False):
                return True
            if self._clock() >= limit:
                logger.warning("[fish_gate] Fish 기동 대기 시간 초과(%.0fs)", self.start_max_sec)
                return False
            await self._sleep(self.start_poll_sec)

    async def _sleep_checking_health(self, label: str, deadline: float) -> bool:
        """recheck_sec 동안 heartbeat_sec 단위로 쪼개 자며 heartbeat 갱신·health 확인. health 성공 시 True."""
        until = min(self._clock() + self.recheck_sec, deadline)
        while self._clock() < until:
            self._stamp(label)
            await self._sleep(min(self.heartbeat_sec, max(until - self._clock(), 0.0)) or 0.0)
            if await self._healthy(use_cache=False):
                return True
        return False


# 프로세스 전역 싱글턴 (fish_client·processor가 공유)
gate = FishGate()
