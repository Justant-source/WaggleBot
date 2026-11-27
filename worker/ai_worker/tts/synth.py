"""Local-TTS 합성 클라이언트 (Fish Speech 대체, P4).

공개 계약 (병렬 작업 간 인터페이스 — 이름·시그니처 변경 금지):
    synthesize(text, scene_type, voice_key, output_path, emotion, post_id) -> Path
    wait_for_tts_server(timeout_sec) -> bool
    TTSUnavailable  — 서버 불가·타임아웃·큐 포화(재시도 소진). 호출처는 일시 장애로 취급(재큐).

흐름: prenormalize(앱 고유 전처리) → resolve_voice(M1~F5) → POST /v1/jobs
      (normalize.profile, chunk max_chars 120, loudnorm -16, speed=TTS_SPEED) → 대기 → wav 저장.
서버가 정규화·청크 분할·후처리를 담당하므로 로컬 분할·품질 재시도·웜업·게이트는 없다.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import time
import uuid
from pathlib import Path

import config.settings as _cfg
from ai_worker.tts.local_tts_client import (
    ConnectionFailed,
    InvalidRequest,
    JobFailed,
    LocalTTS,
    LocalTTSError,
    RateLimited,
    RequestTimeout,
    ServerError,
    Unavailable,
    WaitTimeout,
)
from ai_worker.tts.prenorm import prenormalize
from ai_worker.tts.voice_resolver import resolve_voice

logger = logging.getLogger(__name__)

_CHUNK_MAX_CHARS = 120
_LOUDNORM = {"enabled": True, "i": -16, "tp": -1.5}
_READY_POLL_SEC = 2.0
_SPEECH_CHAR = re.compile(r"[0-9A-Za-z가-힣]")

# 일시 장애로 취급할 클라이언트 예외 (재시도 소진 후 도달)
_TRANSIENT = (ConnectionFailed, RequestTimeout, RateLimited, Unavailable, ServerError, WaitTimeout)


class TTSUnavailable(Exception):
    """Local-TTS 서버 불가·타임아웃·큐 포화(재시도 소진). 포스트 FAILED가 아니라 대기·재큐 대상."""


class TTSError(RuntimeError):
    """재시도해도 소용없는 합성 실패(요청 거부·job 영구 실패)."""


def _new_client() -> LocalTTS:
    """설정 기반 클라이언트 생성. 테스트는 이 함수를 monkeypatch해 transport를 주입한다."""
    return LocalTTS(
        _cfg.TTS_SERVER_URL,
        client=_cfg.TTS_CLIENT_ID,
        token=_cfg.TTS_SERVER_TOKEN or None,
        timeout=float(_cfg.TTS_SERVER_TIMEOUT_SEC),
        max_retries=int(_cfg.TTS_SERVER_RETRIES),
    )


def build_options(voice: str, request_id: str) -> dict:
    """POST /v1/jobs options 본문. request_id는 클라이언트가 options.request_id로 옮긴다."""
    normalize: dict = {"enabled": True}
    if _cfg.TTS_PROFILE:
        normalize["profile"] = _cfg.TTS_PROFILE
    return {
        "voice": voice,
        "lang": "ko",
        "speed": float(_cfg.TTS_SPEED),
        "normalize": normalize,
        "chunk": {"mode": "max_chars", "max_chars": _CHUNK_MAX_CHARS},
        "postprocess": {"loudnorm": dict(_LOUDNORM)},
        "output": {"format": "wav"},
    }


def _synthesize_blocking(text: str, voice: str, output_path: Path, request_id: str,
                         scene_type: str) -> Path:
    t0 = time.monotonic()
    options = build_options(voice, request_id)
    try:
        with _new_client() as c:
            job = c.create_job(text, options, request_id=request_id,
                               idempotency=request_id)  # 서버: Idempotency-Key == options.request_id
            job_id = job["id"]
            try:
                st = c.wait(job_id, timeout=float(_cfg.TTS_SERVER_MAX_WAIT_SEC))
            except WaitTimeout:
                try:
                    c.cancel(job_id)
                except LocalTTSError:
                    pass
                raise
            audio = c.audio(job_id)
            try:
                c.delete(job_id)
            except LocalTTSError:
                pass
    except _TRANSIENT as exc:
        raise TTSUnavailable(f"Local-TTS 일시 장애({type(exc).__name__}): {exc} [{request_id}]") from exc
    except JobFailed as exc:
        if exc.retryable:
            raise TTSUnavailable(f"Local-TTS job 일시 실패: {exc} [{request_id}]") from exc
        raise TTSError(f"Local-TTS job 실패: {exc} [{request_id}]") from exc
    except InvalidRequest as exc:
        if exc.code == "empty_input":
            raise ValueError(f"TTS 입력 텍스트가 서버 정규화 후 비어있음 [{request_id}]") from exc
        raise TTSError(f"Local-TTS 요청 거부: {exc}") from exc
    except LocalTTSError as exc:
        raise TTSError(f"Local-TTS 오류: {exc}") from exc

    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = output_path.with_name(output_path.name + ".part")
    tmp.write_bytes(audio)
    tmp.replace(output_path)
    logger.info(
        "TTS 생성 완료: req=%s scene=%s voice=%s text=%d자 dur=%s → %s (%dKB, %.1fs)",
        request_id, scene_type, voice, len(text), (st.get("result") or {}).get("duration_sec", "?"),
        output_path.name, len(audio) // 1024, time.monotonic() - t0,
    )
    return output_path


async def synthesize(
    text: str,
    scene_type: str = "image_text",
    voice_key: str | None = None,
    output_path: Path | None = None,
    emotion: str = "",
    post_id: int | None = None,
) -> Path:
    """Local-TTS로 음성을 합성해 wav 경로를 반환한다.

    Args:
        text:       읽을 텍스트
        scene_type: 씬 타입 (로깅·request_id용)
        voice_key:  보이스 키(레거시 키 또는 M1~F5). None이면 post_id 시드 결정적 랜덤.
        output_path: 저장 경로 (None이면 /tmp 임시파일)
        emotion:    호환용 — 무시된다(감정 마커 폐기).
        post_id:    보이스 시드·request_id용

    Raises:
        ValueError:     전처리 후 읽을 내용이 없음
        TTSUnavailable: 서버 불가·타임아웃·큐 포화(재시도 소진) — 일시 장애
        TTSError:       요청 거부·job 영구 실패
    """
    prepared = prenormalize(text).strip()
    if not _SPEECH_CHAR.search(prepared):
        logger.warning("TTS 스킵: 전처리 후 빈 텍스트 (원문: '%s')", text[:50])
        raise ValueError(f"TTS 입력 텍스트가 정규화 후 비어있음 (원문: '{text[:50]}')")

    voice = resolve_voice(voice_key, post_id)
    if output_path is None:
        digest = hashlib.md5(f"{voice}|{prepared}".encode()).hexdigest()[:16]
        output_path = Path(f"/tmp/tts_{digest}.wav")
    request_id = f"wb-{post_id if post_id is not None else 'x'}-{scene_type}-{uuid.uuid4().hex[:8]}"
    return await asyncio.to_thread(
        _synthesize_blocking, prepared, voice, Path(output_path), request_id, scene_type,
    )


async def wait_for_tts_server(timeout_sec: float | None = None) -> bool:
    """Local-TTS 서버가 준비(/readyz)될 때까지 대기. 준비되면 True, 시간 초과 시 False."""
    limit = float(_cfg.TTS_SERVER_MAX_WAIT_SEC if timeout_sec is None else timeout_sec)
    deadline = time.monotonic() + limit

    def _ready() -> bool:
        with _new_client() as c:
            return c.ready()

    while True:
        try:
            if await asyncio.to_thread(_ready):
                logger.info("Local-TTS 서버 준비 완료 (%s)", _cfg.TTS_SERVER_URL)
                return True
        except Exception as exc:  # noqa: BLE001 — 대기 루프는 어떤 오류에도 죽지 않는다
            logger.debug("Local-TTS 준비 확인 오류: %s", exc)
        if time.monotonic() >= deadline:
            logger.error("Local-TTS 서버 대기 시간 초과 (%.0fs): %s", limit, _cfg.TTS_SERVER_URL)
            return False
        await asyncio.sleep(min(_READY_POLL_SEC, max(deadline - time.monotonic(), 0.0)))
