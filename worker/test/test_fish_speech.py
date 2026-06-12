"""OpenAudio S1 TTS 통합 테스트 (라이브 — fish-speech 서버 필요).

새 fish_client.synthesize() 경로를 직접 호출해 reference_id 클로닝·감정 마커·
장문 분할·후처리(loudnorm/배속)를 한 번에 검증한다.

실행 (ai_worker 컨테이너 내부 — FISH_SPEECH_URL=http://fish-speech:8080):
    docker compose -f env/docker-compose.yml exec ai_worker python test/test_fish_speech.py

호스트에서 직접 실행 시 (포트 8082 매핑):
    python worker/test/test_fish_speech.py --url http://localhost:8082

사전 조건:
  - fish-speech 컨테이너 healthy (OpenAudio S1-mini 로드)
  - assets/voices/<key>/ 에 참조 음성 등록 (없으면 기본 음색으로 합성됨)

결과물: worker/test/test_tts_output/ (WAV + summary.json + 로그)
"""
import argparse
import asyncio
import json
import logging
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent  # /app (worker/)
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import httpx

from config.settings import FISH_SPEECH_URL, TTS_OUTPUT_FORMAT, VOICE_DEFAULT, VOICE_PRESETS

OUTPUT_DIR = _ROOT / "test" / "test_tts_output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-5s %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(OUTPUT_DIR / "test_log.txt", mode="w", encoding="utf-8"),
    ],
)
logger = logging.getLogger("fish_test")

# CLI에서 덮어쓸 수 있는 서버 URL (기본: 컨테이너 내부 주소)
SERVER_URL = FISH_SPEECH_URL

TEST_SENTENCES = [
    "안녕하세요, 오늘 소개할 이야기는 정말 놀라운 사연입니다.",
    "어제 퇴근길에 편의점에서 있었던 일인데, 진짜 소름 돋았어요.",
    "3년 전에 200만원짜리 중고차를 샀는데, 알고보니 사고차였습니다.",
    "이 영상이 도움이 되셨다면 좋아요와 구독 부탁드립니다. 다음에 또 만나요!",
]

LONG_TEXT = (
    "제가 어렸을 때 살던 동네에는 작은 골목길이 하나 있었는데요, "
    "그 골목 끝에는 오래된 구멍가게가 하나 있었습니다. "
    "주인 할머니는 늘 정정하셨고, 동네 아이들에게 항상 사탕을 하나씩 쥐여 주시곤 했어요. "
    "그런데 어느 날 갑자기 그 가게가 문을 닫았고, 할머니도 보이지 않으셨습니다. "
    "한참이 지나서야 우리는 그 사정을 알게 되었습니다."
)


def _wav_secs(path: Path) -> float:
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            capture_output=True, text=True, check=True,
        )
        return round(float(r.stdout.strip()), 2)
    except Exception:
        return 0.0


async def check_server() -> bool:
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{SERVER_URL}/")
            logger.info("서버 응답: HTTP %d (%s)", r.status_code, SERVER_URL)
            return True
    except Exception as exc:
        logger.error("서버 연결 실패 (%s): %s", SERVER_URL, exc)
        return False


async def test_basic(synthesize) -> list[dict]:
    logger.info("=" * 60)
    logger.info("기본 합성 (%d문장, voice=%s)", len(TEST_SENTENCES), VOICE_DEFAULT)
    results = []
    for i, text in enumerate(TEST_SENTENCES, start=1):
        out = OUTPUT_DIR / f"basic_{i}.wav"
        t0 = time.time()
        try:
            await synthesize(text=text, output_path=out)
            secs = _wav_secs(out)
            spc = round(secs / max(len(text), 1), 3)
            logger.info("  [%d] %.1fs (%.3f초/자, %.1fs 소요): %s", i, secs, spc, time.time() - t0, text[:30])
            results.append({"id": i, "text": text, "secs": secs, "secs_per_char": spc, "status": "ok"})
        except Exception as exc:
            logger.error("  [%d] 실패: %s", i, exc)
            results.append({"id": i, "text": text, "status": f"error: {exc}"})
    return results


async def test_emotion(synthesize) -> list[dict]:
    logger.info("=" * 60)
    logger.info("감정 마커 A/B (동일 문장, 마커별)")
    text = "정말 믿을 수 없는 일이 벌어졌어요."
    results = []
    for emo in ("", "sad", "whispering", "surprised"):
        out = OUTPUT_DIR / f"emotion_{emo or 'none'}.wav"
        try:
            await synthesize(text=text, output_path=out, emotion=emo)
            secs = _wav_secs(out)
            logger.info("  emotion=%-10s → %.1fs (%s)", emo or "(none)", secs, out.name)
            results.append({"emotion": emo, "secs": secs, "status": "ok"})
        except Exception as exc:
            logger.error("  emotion=%s 실패: %s", emo, exc)
            results.append({"emotion": emo, "status": f"error: {exc}"})
    return results


async def test_long_split(synthesize) -> dict:
    logger.info("=" * 60)
    logger.info("장문 분할 합성 (%d자 → 세그먼트 분할·병합)", len(LONG_TEXT))
    out = OUTPUT_DIR / "long_split.wav"
    try:
        await synthesize(text=LONG_TEXT, output_path=out)
        secs = _wav_secs(out)
        logger.info("  %d자 → %.1fs (%s)", len(LONG_TEXT), secs, out.name)
        return {"chars": len(LONG_TEXT), "secs": secs, "status": "ok"}
    except Exception as exc:
        logger.error("  실패: %s", exc)
        return {"chars": len(LONG_TEXT), "status": f"error: {exc}"}


async def test_voices(synthesize) -> list[dict]:
    logger.info("=" * 60)
    logger.info("음성별 클로닝 (등록된 voice 프리셋)")
    text = "안녕하세요, 이 목소리로 합성한 테스트입니다."
    results = []
    for vk in VOICE_PRESETS:
        out = OUTPUT_DIR / f"voice_{vk}.wav"
        try:
            await synthesize(text=text, voice_key=vk, output_path=out)
            secs = _wav_secs(out)
            logger.info("  voice=%-10s → %.1fs", vk, secs)
            results.append({"voice": vk, "secs": secs, "status": "ok"})
        except Exception as exc:
            logger.error("  voice=%s 실패: %s", vk, exc)
            results.append({"voice": vk, "status": f"error: {exc}"})
    return results


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", help="fish-speech 서버 URL 오버라이드 (예: http://localhost:8082)")
    parser.add_argument("--skip-voices", action="store_true", help="음성별 클로닝 테스트 생략")
    args = parser.parse_args()

    global SERVER_URL
    if args.url:
        SERVER_URL = args.url
        # fish_client는 config의 FISH_SPEECH_URL을 사용하므로 환경에 맞춰 실행 권장.
        logger.warning("--url 지정됨(%s). fish_client.synthesize는 config FISH_SPEECH_URL(%s)을 사용함에 유의.",
                       args.url, FISH_SPEECH_URL)

    logger.info("OpenAudio S1 TTS 통합 테스트 — 서버 %s, 출력 %s", SERVER_URL, OUTPUT_DIR)

    if not await check_server():
        logger.error("서버 연결 불가 — 테스트 중단 (fish-speech healthy 확인)")
        sys.exit(1)

    from ai_worker.tts.fish_client import synthesize

    summary: dict = {"timestamp": datetime.now().isoformat(), "server": SERVER_URL}
    summary["basic"] = await test_basic(synthesize)
    summary["emotion"] = await test_emotion(synthesize)
    summary["long_split"] = await test_long_split(synthesize)
    if not args.skip_voices:
        summary["voices"] = await test_voices(synthesize)

    (OUTPUT_DIR / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8",
    )

    logger.info("=" * 60)
    ok = sum(1 for r in summary["basic"] if r.get("status") == "ok")
    logger.info("기본 합성: %d/%d 성공", ok, len(summary["basic"]))
    logger.info("결과: %s (WAV + summary.json + test_log.txt)", OUTPUT_DIR)


if __name__ == "__main__":
    asyncio.run(main())
