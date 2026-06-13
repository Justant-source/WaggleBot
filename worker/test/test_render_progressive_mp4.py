"""
댓글·채팅 점진적 낭독 E2E 렌더 테스트.

사용법 (ai_worker 컨테이너 안에서):
  docker exec waggle_ai_worker python -m test.test_render_progressive_mp4

출력:
  /app/media/tmp/progressive_test/progressive_test.mp4
  /app/media/tmp/progressive_test/frames/ 디렉터리 내 PNG들
"""
import logging
import sys
import time
import types
from datetime import datetime
from pathlib import Path

# 프로젝트 루트(/app/worker)를 sys.path에 추가 — 직접 실행 시 패키지 경로 확보
_ROOT = Path(__file__).resolve().parent.parent  # /app/worker
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# 패키지 절대경로 import (ai_worker 컨테이너 기준)
from ai_worker.scene.director import SceneDecision
from ai_worker.renderer.layout import render_layout_video_from_scenes

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

OUTPUT_DIR = Path("/app/media/tmp/progressive_test")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def _make_stub_post() -> types.SimpleNamespace:
    """DB 없이 렌더러에 넘길 최소 Post-like 객체 생성.

    SQLAlchemy ORM 인스턴스 대신 SimpleNamespace 사용.
    render_layout_video_from_scenes는 post 타입을 isinstance로 체크하지 않으므로
    덕타이핑으로 동작한다.
    """
    return types.SimpleNamespace(
        id=9999,
        title="점진적 낭독 테스트 — 댓글·채팅",
        site_code="test",
        origin_id="test_9999",
        images=[],
        stats={"views": 12000, "comments_count": 3},
        created_at=datetime(2026, 6, 14, 10, 0, 0),
        author=None,
    )


def _make_scenes() -> list[SceneDecision]:
    """합성 씬 리스트 — intro + 댓글 3개 씬 + 채팅 4개 씬 + outro.

    SceneDecision은 dataclass이므로 생성자 키워드 인수로 직접 주입한다.
    comment_items·chat_messages는 각각 "comments"/"chat" 씬 전용 필드.
    """
    return [
        # ── 인트로 ──────────────────────────────────────────────────────────
        SceneDecision(
            type="intro",
            text_lines=["이건 진짜 있었던 일인데... 믿기지 않으실 거예요."],
            image_url=None,
            mood="shock",
        ),
        # ── 댓글 씬: 3개 댓글 → 3개 plan 엔트리 → 3프레임 누적 표시 ──────────
        SceneDecision(
            type="comments",
            text_lines=[],          # comments 씬은 text_lines 미사용
            image_url=None,
            mood="shock",
            comment_items=[
                {
                    "author": "김철수",
                    "content": "진짜 말도 안 되는 상황이네요 ㄷㄷ",
                    "likes": 248,
                    "is_best": True,
                    "voice": "manbo",
                },
                {
                    "author": "이영희",
                    "content": "저도 비슷한 경험 있어요. 정말 황당했죠.",
                    "likes": 156,
                    "is_best": False,
                    "voice": "anna",
                },
                {
                    "author": "박민준",
                    "content": "ㅋㅋㅋㅋ 이게 실화라고요?? 대박",
                    "likes": 89,
                    "is_best": False,
                    "voice": "han",
                },
            ],
        ),
        # ── 채팅 씬: 4개 메시지 → 4개 plan 엔트리 → 4프레임 누적 표시 ────────
        SceneDecision(
            type="chat",
            text_lines=[],          # chat 씬은 text_lines 미사용
            image_url=None,
            mood="shock",
            chat_messages=[
                {
                    "sender": "친구",
                    "text": "야 너 그거 들었어?",
                    "is_mine": False,
                    "voice": "yohan",
                },
                {
                    "sender": "나",
                    "text": "무슨 일인데??",
                    "is_mine": True,
                    "voice": None,  # is_mine=True → 내레이터 목소리 (TTS default)
                },
                {
                    "sender": "친구",
                    "text": "걔가 진짜로 그랬다고 ㄷㄷ",
                    "is_mine": False,
                    "voice": "yohan",
                },
                {
                    "sender": "나",
                    "text": "헐 진짜?? 말도 안 돼",
                    "is_mine": True,
                    "voice": None,  # is_mine=True → 내레이터 목소리 (TTS default)
                },
            ],
        ),
        # ── 아웃트로 ────────────────────────────────────────────────────────
        SceneDecision(
            type="outro",
            text_lines=["여러분이라면 어떻게 하셨을까요?"],
            image_url=None,
            mood="shock",
        ),
    ]


def main() -> None:
    t0 = time.time()
    logger.info("=== 점진적 낭독 E2E 렌더 테스트 시작 ===")

    post = _make_stub_post()
    scenes = _make_scenes()

    out_path = OUTPUT_DIR / "progressive_test.mp4"

    logger.info("씬 수: %d", len(scenes))
    logger.info("댓글 씬: %d개 댓글", len(scenes[1].comment_items or []))
    logger.info("채팅 씬: %d개 메시지", len(scenes[2].chat_messages or []))

    # render_layout_video_from_scenes 시그니처:
    #   (post, scenes, output_path=None, save_tts_cache=None,
    #    tts_audio_cache=None, voice_key=None) -> Path
    # narrator_voice 파라미터는 없음 — voice_key로 기본 TTS 목소리 지정
    result = render_layout_video_from_scenes(
        post=post,
        scenes=scenes,
        output_path=out_path,
    )

    elapsed = time.time() - t0
    result_path = Path(result) if result else None

    if result_path and result_path.exists():
        size_mb = result_path.stat().st_size / 1024 / 1024
        logger.info("=== 렌더 완료 ===")
        logger.info("출력: %s", result_path)
        logger.info("크기: %.2f MB", size_mb)
        logger.info("소요: %.1f초", elapsed)
        logger.info("")
        logger.info("=== 수동 확인 항목 ===")
        logger.info("1. 댓글 프레임: 3프레임 (1개→2개→3개 누적 표시, 각각 TTS 낭독)")
        logger.info("2. 채팅 프레임: 4프레임 (버블 1개씩 append, 각각 TTS 낭독)")
        logger.info("3. 화자별 목소리 다름 (댓글: manbo/anna/han, 채팅: yohan/내레이터)")
        logger.info(
            "4. h264_nvenc 단일패스 확인: "
            "docker compose logs ai_worker | grep nvenc"
        )
        logger.info(
            "5. 영상 재생: /app/media/tmp/progressive_test/progressive_test.mp4"
        )
    else:
        logger.error("=== 렌더 실패 ===")
        raise RuntimeError(f"render_layout_video_from_scenes returned: {result}")


if __name__ == "__main__":
    main()
