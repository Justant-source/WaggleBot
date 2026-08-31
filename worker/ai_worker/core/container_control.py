"""Docker 컨테이너 제어 — Fish Speech VRAM 실제 해제/복구.

공식 fish-speech 이미지(fishaudio/fish-speech:server-cuda)에는 HTTP 기반
/v1/models/unload 엔드포인트가 없다(404). S1-mini는 유휴 VRAM이 작아(~3-5GB)
이 문제가 드러나지 않았지만, S2-pro는 유휴 상태에서도 ~20GB를 점유해
ComfyUI Phase 7(GGUF UNet ~12.7GB) 진입 시 OOM 위험이 확정적이다.
(경위: .result/tts/failures-2026-08-09.md 실패 9)

이 모듈은 fish-speech 컨테이너 자체를 stop/start해 VRAM을 실제로 해제·복구한다.

운영 절대 규칙: TTS는 `fish-speech`(S2-pro) 단일 인스턴스만. S1-mini를 VRAM에
올리지 말고, `fish-speech-s2` 등 병렬 컨테이너를 띄우지 말 것(2026-08-10 OOM).
ai_worker 컨테이너에 /var/run/docker.sock이 마운트돼 있어야 동작한다
(env/docker-compose.yml의 ai_worker 서비스 volumes + group_add 참조).
"""

import asyncio
import logging
import time

logger = logging.getLogger(__name__)

FISH_SPEECH_CONTAINER = "fish-speech"
_STOP_TIMEOUT_S = 15
_START_HEALTHY_TIMEOUT_S = 240
_MAX_RETRIES = 3


def _get_docker_client():
    import docker
    return docker.from_env()


async def stop_fish_speech() -> bool:
    """fish-speech 컨테이너를 정지해 VRAM을 실제로 해제한다.

    Returns:
        정지(또는 이미 정지 상태) 확인 성공 여부.
    """
    def _stop() -> bool:
        client = _get_docker_client()
        try:
            container = client.containers.get(FISH_SPEECH_CONTAINER)
        except Exception:
            logger.error("[container_control] fish-speech 컨테이너를 찾을 수 없음")
            return False
        if container.status != "running":
            logger.info(
                "[container_control] fish-speech 이미 정지 상태(%s)", container.status,
            )
            return True
        container.stop(timeout=_STOP_TIMEOUT_S)
        logger.info("[container_control] fish-speech 정지 완료")
        return True

    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            if await asyncio.to_thread(_stop):
                return True
        except Exception as e:
            logger.warning(
                "[container_control] fish-speech 정지 실패(%d/%d): %s",
                attempt, _MAX_RETRIES, e,
            )
        await asyncio.sleep(2)

    logger.error("[container_control] fish-speech 정지 %d회 모두 실패", _MAX_RETRIES)
    return False


async def start_fish_speech(
    wait_healthy: bool = True, timeout: float = _START_HEALTHY_TIMEOUT_S,
) -> bool:
    """fish-speech 컨테이너를 재기동하고, healthy가 될 때까지 대기한다.

    Returns:
        재기동(+ healthy 대기) 성공 여부. False면 다음 TTS 요청이 실패할 수 있으므로
        호출부에서 반드시 ERROR 레벨로 로그를 남겨야 한다.
    """
    def _start() -> None:
        client = _get_docker_client()
        container = client.containers.get(FISH_SPEECH_CONTAINER)
        if container.status != "running":
            container.start()
            logger.info("[container_control] fish-speech 재기동 시작")

    def _is_healthy() -> bool:
        client = _get_docker_client()
        container = client.containers.get(FISH_SPEECH_CONTAINER)
        container.reload()
        health = container.attrs.get("State", {}).get("Health", {}).get("Status")
        return health == "healthy"

    started = False
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            await asyncio.to_thread(_start)
            started = True
            break
        except Exception as e:
            logger.warning(
                "[container_control] fish-speech 재기동 실패(%d/%d): %s",
                attempt, _MAX_RETRIES, e,
            )
            await asyncio.sleep(2)

    if not started:
        logger.error("[container_control] fish-speech 재기동 %d회 모두 실패", _MAX_RETRIES)
        return False

    if not wait_healthy:
        return True

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if await asyncio.to_thread(_is_healthy):
                logger.info("[container_control] fish-speech healthy 확인")
                return True
        except Exception as e:
            logger.debug("[container_control] health 확인 중 오류(재시도): %s", e)
        await asyncio.sleep(3)

    logger.error(
        "[container_control] fish-speech healthy 대기 타임아웃(%.0fs)", timeout,
    )
    return False
