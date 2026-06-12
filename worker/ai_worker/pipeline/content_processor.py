"""ai_worker/pipeline/content_processor.py — Phase 1~7 오케스트레이션

각 Phase의 실제 로직은 해당 도메인 모듈에 위치한다.
이 파일은 Phase 실행 순서와 VRAM 전환만 담당한다.

Phase 1: scene.analyzer.analyze_resources()
Phase 2: script.chunker.chunk_with_llm()
Phase 3: scene.validator.validate_and_fix()
Phase 4: scene.director.SceneDirector.direct()
Phase 4.5: scene.director.assign_video_modes()
Phase 5: tts.fish_client.synthesize()
Phase 6: video.prompt_engine.VideoPromptEngine.generate_batch()
Phase 7: video.manager.VideoManager.generate_all_clips()
"""
import asyncio
import collections
import json as _json
import logging
from datetime import datetime
from pathlib import Path

from ai_worker.script.chunker import chunk_with_llm
from ai_worker.scene.analyzer import ResourceProfile, analyze_resources
from ai_worker.scene.director import SceneDecision, SceneDirector
from ai_worker.scene.validator import validate_and_fix
from ai_worker.tts.fish_client import synthesize
from db.models import Post
from db.session import SessionLocal

logger = logging.getLogger(__name__)


def _touch_post(post_id: int) -> None:
    """Phase 경계 하트비트 — updated_at을 현재 UTC 시각으로 터치.

    PROCESSING 상태 포스트가 멈춰도 감지할 수 있도록 각 Phase 완료 시점마다 호출한다.
    DB 오류는 로그만 남기고 파이프라인을 중단하지 않는다.
    """
    try:
        with SessionLocal() as db:
            db.query(Post).filter(Post.id == post_id).update(
                {"updated_at": datetime.utcnow()}, synchronize_session=False
            )
            db.commit()
    except Exception as _exc:
        logger.warning("[heartbeat] updated_at 터치 실패 (post_id=%d): %s", post_id, _exc)


async def process_content(post, images: list[str], cfg: dict | None = None) -> list[SceneDecision]:
    """콘텐츠 처리 전체 파이프라인.

    Args:
        post:   Post 객체 (post.content, post.title 사용)
        images: 이미지 URL/경로 목록
        cfg:    파이프라인 설정 dict (선택). comment_voices 등.

    Returns:
        렌더러에 전달할 SceneDecision 목록.
        Phase 5 이후 scene.text_lines 요소는 {"text": str, "audio": str|None} dict.

    Raises:
        ConnectionError: LLM worker 통신 오류
        ValueError: 대본 필수 키 누락 등 검증 실패
    """
    _cfg = cfg or {}
    post_id: int = post.id
    comment_voices: list[str] = _json.loads(_cfg.get("comment_voices", "[]"))
    # ── Phase 1: 자원 분석 ────────────────────────────────────────
    profile: ResourceProfile = analyze_resources(post, images)
    logger.info(
        "[content_processor] Phase 1 완료: 전략=%s 이미지=%d 예상문장≈%d",
        profile.strategy, profile.image_count, profile.estimated_sentences,
    )
    _touch_post(post_id)

    # ── Phase 2: LLM 청킹 (의미 단위) ────────────────────────────
    # 제목·베스트 댓글·성과 피드백을 LLM에 전달 (후킹·댓글 인용·피드백 루프 활성화)
    from analytics.feedback import build_extra_instructions

    try:
        _best = sorted(post.comments, key=lambda c: c.likes, reverse=True)[:5]
        _comment_texts = [f"{c.author}: {c.content[:100]}" for c in _best]
    except Exception:
        logger.debug("[content_processor] 베스트 댓글 로드 실패 — 생략", exc_info=True)
        _comment_texts = []
    _extra = build_extra_instructions(post_id)  # 세션 미보유 → helper 내부 SessionLocal 사용

    llm_output: dict = await chunk_with_llm(
        post.content or "", profile, post_id=post_id, extended=True,
        title=post.title or "",
        best_comments=_comment_texts,
        extra_instructions=_extra or "",
    )

    # ── Phase 3: 물리적 검증 (max_chars 보정) ─────────────────────
    script: dict = validate_and_fix(llm_output)
    logger.info(
        "[content_processor] Phase 3 완료: hook(%d자) + body(%d줄) + closer(%d자)",
        len(script.get("hook", "")),
        len(script.get("body", [])),
        len(script.get("closer", "")),
    )
    _touch_post(post_id)

    # ── Phase 4: 씬 배분 ──────────────────────────────────────────
    from config.settings import VIDEO_GEN_ENABLED, MEDIA_DIR

    # LLM Scene Director용 이미지 캐시 디렉터리 (Phase 4 + 4.5 공유)
    image_cache_dir = MEDIA_DIR / "tmp" / f"vid_image_cache_{post.id}"
    if VIDEO_GEN_ENABLED:
        image_cache_dir.mkdir(parents=True, exist_ok=True)

    director = SceneDirector(
        profile, images, script,
        mood=script.get("mood", "daily"),
        comment_voices=comment_voices,
        post_id=post.id,
        image_cache_dir=image_cache_dir if VIDEO_GEN_ENABLED else None,
    )
    scenes: list[SceneDecision] = director.direct()

    counter = collections.Counter(s.type for s in scenes)
    logger.info(
        "[content_processor] Phase 4 완료: %d씬 구성 %s",
        len(scenes), dict(counter),
    )
    _touch_post(post_id)

    # ── Phase 4.5: video_mode 할당 ────────────────────────────────
    # LLM Director가 이미 video_mode를 설정한 씬은 assign_video_modes()에서 스킵됨 (안전망).
    if VIDEO_GEN_ENABLED:
        from ai_worker.scene.director import assign_video_modes
        from config.settings import VIDEO_I2V_THRESHOLD

        scenes = assign_video_modes(
            scenes=scenes,
            image_cache_dir=image_cache_dir,
            i2v_threshold=VIDEO_I2V_THRESHOLD,
        )
        logger.info("[content_processor] Phase 4.5 완료: video_mode 할당")
        _touch_post(post_id)
    else:
        logger.info("[content_processor] VIDEO_GEN_ENABLED=false — Phase 4.5 스킵")

    # ── Phase 5 내부 함수 정의 ────────────────────────────────────
    async def _run_tts_phase(scene_list: list[SceneDecision]) -> tuple[int, int]:
        """Phase 5: TTS 사전 생성. (tts_ok, tts_fail) 카운트 반환."""
        ok = 0
        fail = 0
        for scene in scene_list:
            for j, line in enumerate(scene.text_lines):
                text = line if isinstance(line, str) else line.get("text", "")
                try:
                    tts_kwargs: dict = {
                        "text": text,
                        "scene_type": scene.type,
                        "emotion": getattr(scene, "tts_emotion", ""),
                    }
                    if scene.voice_override:
                        tts_kwargs["voice_key"] = scene.voice_override
                    audio_path = await synthesize(**tts_kwargs)
                    scene.text_lines[j] = {"text": text, "audio": str(audio_path)}
                    ok += 1
                except Exception as exc:
                    logger.warning(
                        "[content_processor] TTS 실패 (씬=%s, 줄=%d): %s",
                        scene.type, j, exc,
                    )
                    scene.text_lines[j] = {"text": text, "audio": None}
                    fail += 1
        return ok, fail

    # ── Phase 5 & 6 (VIDEO_GEN_ENABLED일 때 병렬, 아닐 때 Phase 5만 순차) ──
    if VIDEO_GEN_ENABLED:
        from ai_worker.video.prompt_engine import VideoPromptEngine

        body_texts: list[str] = []
        for block in list(script.get("body", [])):
            if isinstance(block, dict):
                body_texts.extend(block.get("lines", []))
            else:
                body_texts.append(str(block))
        body_summary = " ".join(body_texts)[:500]

        prompt_engine = VideoPromptEngine()
        _mood = script.get("mood", "daily")
        _title = post.title or ""
        _post_id_ref = getattr(post, "id", None)

        logger.info("[content_processor] Phase 5 & 6 병렬 시작 (TTS ∥ video_prompt)")

        # Phase 6은 원격 LLM만 사용하므로 GPU 미접촉 → 스레드 풀에서 실행
        _loop = asyncio.get_running_loop()

        async def _run_phase6() -> list[SceneDecision]:
            return await _loop.run_in_executor(
                None,
                lambda: prompt_engine.generate_batch(
                    scenes=scenes,
                    mood=_mood,
                    title=_title,
                    body_summary=body_summary,
                    post_id=_post_id_ref,
                ),
            )

        (tts_ok, tts_fail), scenes = await asyncio.gather(
            _run_tts_phase(scenes),
            _run_phase6(),
        )

        logger.info(
            "[content_processor] Phase 5 완료: TTS 성공=%d 실패=%d",
            tts_ok, tts_fail,
        )
        logger.info(
            "[content_processor] Phase 6 완료: %d개 프롬프트 생성",
            sum(1 for s in scenes if s.video_prompt),
        )
    else:
        # VIDEO_GEN_ENABLED=false — Phase 5만 순차 실행 (기존 동작 유지)
        tts_ok, tts_fail = await _run_tts_phase(scenes)
        logger.info(
            "[content_processor] Phase 5 완료: TTS 성공=%d 실패=%d",
            tts_ok, tts_fail,
        )
        logger.info("[content_processor] VIDEO_GEN_ENABLED=false — Phase 6 스킵")
        body_summary = ""  # Phase 7 스킵 시에도 body_summary 변수 정의

    _touch_post(post_id)

    # ── Phase 7: Video Clip 생성 (GPU 필요, ComfyUI 경유) ─────────
    if VIDEO_GEN_ENABLED:
        import gc

        # ★ 2막 전환: LLM + TTS VRAM 완전 해제 시퀀스
        await _clear_vram_for_video()
        _touch_post(post_id)

        from ai_worker.video.manager import VideoManager
        from ai_worker.video.comfy_client import ComfyUIClient
        from config.settings import (
            get_comfyui_url, VIDEO_GEN_TIMEOUT, VIDEO_GEN_TIMEOUT_DISTILLED,
            VIDEO_RESOLUTION,
            VIDEO_RESOLUTION_FALLBACK, VIDEO_NUM_FRAMES, VIDEO_NUM_FRAMES_FALLBACK,
            VIDEO_NUM_FRAMES_MAX,
            VIDEO_MAX_CLIPS_PER_POST, VIDEO_MAX_RETRY,
            VIDEO_STEPS, VIDEO_STEPS_DISTILLED,
            VIDEO_CFG, VIDEO_CFG_DISTILLED,
            VIDEO_FPS, VIDEO_WORKFLOW_MODE,
        )

        # ★ Phase 7 진입 전 동적 VRAM 확인 (nvidia-smi 기반)
        from ai_worker.core.gpu_manager import GPUMemoryManager
        available_vram = GPUMemoryManager.get_system_available_vram()
        if available_vram is not None and available_vram > 0 and available_vram < 13.0:
            logger.warning(
                "[content_processor] Phase 7 진입 경고: 가용 VRAM %.1fGB < 13GB. "
                "GGUF Q4 로드 중 OOM 발생 가능. 계속 진행합니다.",
                available_vram,
            )
        else:
            logger.info(
                "[content_processor] Phase 7 진입 VRAM 확인: %.1fGB 여유",
                available_vram if available_vram else 0.0,
            )

        logger.info(
            "[content_processor] Phase 7: 비디오 클립 생성 시작 "
            "(VRAM 해제 완료, mode=%s)", VIDEO_WORKFLOW_MODE,
        )

        comfy = ComfyUIClient(base_url=get_comfyui_url())
        video_config = {
            "VIDEO_RESOLUTION": VIDEO_RESOLUTION,
            "VIDEO_RESOLUTION_FALLBACK": VIDEO_RESOLUTION_FALLBACK,
            "VIDEO_NUM_FRAMES": VIDEO_NUM_FRAMES,
            "VIDEO_NUM_FRAMES_FALLBACK": VIDEO_NUM_FRAMES_FALLBACK,
            "VIDEO_NUM_FRAMES_MAX": VIDEO_NUM_FRAMES_MAX,
            "VIDEO_GEN_TIMEOUT": VIDEO_GEN_TIMEOUT,
            "VIDEO_GEN_TIMEOUT_DISTILLED": VIDEO_GEN_TIMEOUT_DISTILLED,
            "VIDEO_MAX_CLIPS_PER_POST": VIDEO_MAX_CLIPS_PER_POST,
            "VIDEO_MAX_RETRY": VIDEO_MAX_RETRY,
            "VIDEO_STEPS": VIDEO_STEPS,
            "VIDEO_STEPS_DISTILLED": VIDEO_STEPS_DISTILLED,
            "VIDEO_CFG": VIDEO_CFG,
            "VIDEO_CFG_DISTILLED": VIDEO_CFG_DISTILLED,
            "VIDEO_FPS": VIDEO_FPS,
            "VIDEO_WORKFLOW_MODE": VIDEO_WORKFLOW_MODE,
        }

        manager = VideoManager(
            comfy_client=comfy,
            prompt_engine=prompt_engine,
            config=video_config,
        )

        def _on_scene_done(scene_idx: int, clip_path: str) -> None:
            _touch_post(post_id)

        scenes = await manager.generate_all_clips(
            scenes=scenes,
            mood=script.get("mood", "daily"),
            post_id=post.id,
            title=post.title or "",
            body_summary=body_summary,
            on_scene_complete=_on_scene_done,
        )

        try:
            import torch
            torch.cuda.empty_cache()
        except Exception:
            pass
        gc.collect()

        video_ok = sum(1 for s in scenes if s.video_clip_path)
        video_fail = sum(1 for r in manager.results if not r.success)
        logger.info(
            "[content_processor] Phase 7 완료: 성공=%d, 실패(삭제)=%d, 최종 씬 수=%d",
            video_ok, video_fail, len(scenes),
        )
        _touch_post(post_id)
    else:
        logger.info("[content_processor] VIDEO_GEN_ENABLED=false — Phase 7 스킵")

    return scenes


async def _clear_vram_for_video() -> None:
    """Phase 7 진입 전 — LLM/TTS VRAM 완전 해제 시퀀스.

    1막(TTS) → 2막(비디오) 전환 시 Fish Speech의 VRAM을
    명시적으로 해제하고, nvidia-smi로 실제 여유 VRAM을 확인한다.
    """
    import gc

    from ai_worker.core.gpu_manager import GPUMemoryManager, get_gpu_manager
    from config.settings import FISH_SPEECH_URL

    logger.info("[VRAM] 2막 전환 시작: TTS VRAM 해제 시퀀스")

    # 1) Fish Speech 모델 언로드 — 컨테이너는 유지하되 GPU 메모리만 해제
    try:
        import httpx
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{FISH_SPEECH_URL}/v1/models/unload",
                timeout=10.0,
            )
            if resp.status_code in (200, 404):
                logger.info("[VRAM] Fish Speech 모델 언로드 완료")
            else:
                logger.warning("[VRAM] Fish Speech 언로드 응답: %d", resp.status_code)
    except Exception as e:
        logger.warning("[VRAM] Fish Speech 언로드 실패 (계속 진행): %s", e)

    # 2) ai_worker 자체 PyTorch 캐시 정리
    try:
        import torch
        torch.cuda.empty_cache()
    except Exception:
        pass
    gc.collect()

    # 3) 실제 여유 VRAM 확인 (nvidia-smi 기반 — 모든 프로세스 포함)
    _gm = get_gpu_manager()
    free_vram = GPUMemoryManager.get_system_available_vram()
    if free_vram > 0:
        logger.info("[VRAM] 시스템 여유 VRAM: %.1fGB", free_vram)
        if free_vram < 20.0:
            logger.warning(
                "[VRAM] 여유 VRAM 부족 (%.1fGB < 20GB) — 긴급 정리 시도", free_vram,
            )
            _gm.emergency_cleanup()
            free_vram = GPUMemoryManager.get_system_available_vram()
            logger.info("[VRAM] 긴급 정리 후 여유 VRAM: %.1fGB", free_vram)
    else:
        # nvidia-smi 사용 불가 시 PyTorch 기준 폴백
        free_vram = _gm.get_available_vram()
        logger.info("[VRAM] PyTorch 기준 여유 VRAM: %.1fGB (nvidia-smi 사용 불가)", free_vram)

    logger.info("[VRAM] 2막 전환 완료: %.1fGB 여유", free_vram)
