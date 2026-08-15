"""
AI Worker Processor with Robust Error Handling

견고한 에러 핸들링 및 재시도 메커니즘
"""

import hashlib
import json
import logging
import shutil
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from ai_worker.core.gpu_manager import get_gpu_manager, ModelType
from ai_worker.core.progress import (
    stamp_progress, clear_checkpoint_keep_progress, load_render_checkpoint,
    save_render_checkpoint, save_generation_diagnostics, get_runtime_state,
)
from ai_worker.script.client import generate_script
from ai_worker.renderer.thumbnail import generate_thumbnail, get_thumbnail_path
from ai_worker.tts.fish_client import synthesize as tts_synthesize
from db.models import ScriptData
from config.settings import (
    MAX_RETRY_COUNT,
    MEDIA_DIR,
    TTS_OUTPUT_FORMAT,
    TTS_SPEED,
    VOICE_DEFAULT,
    load_pipeline_config,
)
from db.models import Content, Post, PostStatus
from db.session import SessionLocal

logger = logging.getLogger(__name__)

_TTS_POST_PROCESS_CACHE_VERSION = "pp_v6"


def _save_generation_diagnostics(session: Session, post_id: int, diagnostics: dict) -> None:
    """Persist safe quality facts outside the shared contents JSON row."""
    save_generation_diagnostics(post_id, diagnostics)



def _tts_cache_key(voice_id: str, text: str) -> str:
    """Return the cache identity for audio-affecting TTS post-processing.

    Keep a named post-process version as an explicit invalidation boundary, and
    include the active speed to protect future configuration changes as well.
    """
    return f"{voice_id}:{text}:{TTS_SPEED:.3f}:{_TTS_POST_PROCESS_CACHE_VERSION}"



def _resolve_post_comment_voices(post_id: int) -> list[str] | None:
    """variant_config.comment_voices — 어드민이 고른 댓글 TTS 풀 (최대 5).

    None → SceneDirector가 pipeline.json comment_voices 사용.
    [] → 풀 없음(내레이터 폴백). 비어 있지 않으면 그 목록만 사용.
    """
    cfg = _resolve_post_variant_config(post_id)
    raw = cfg.get("comment_voices") or cfg.get("commentVoices") or cfg.get("comment_tts_voices")
    if raw is None:
        return None
    voices: list[str] = []
    if isinstance(raw, list):
        voices = [str(v).strip() for v in raw if str(v).strip()]
    elif isinstance(raw, str):
        s = raw.strip()
        if s.startswith("["):
            try:
                import json as _json
                parsed = _json.loads(s)
                if isinstance(parsed, list):
                    voices = [str(v).strip() for v in parsed if str(v).strip()]
            except Exception:
                voices = []
        else:
            voices = [p.strip() for p in s.replace(";", ",").split(",") if p.strip()]
    # cap 5
    return voices[:5]

def _resolve_post_voice(post_id: int) -> str | None:
    """게시글별 TTS 보이스 조회 (없으면 None → 전역 설정 사용).

    우선순위:
      1) contents.variant_config.tts_voice — 외부 ingest(Again Spring 어드민 선택) SSOT
      2) contents.tts_voice 컬럼
    variant를 컬럼보다 앞에 두는 이유: 파이프라인 기본값(yohan 등)으로 컬럼이
    덮어써진 뒤에도 어드민이 고른 음성을 복구할 수 있어야 한다.
    """
    try:
        with SessionLocal() as db:
            ct = db.query(Content).filter_by(post_id=post_id).first()
            if ct is None:
                return None
            cfg = ct.variant_config if isinstance(ct.variant_config, dict) else {}
            for key in ("tts_voice", "ttsVoice"):
                raw = cfg.get(key)
                if isinstance(raw, str) and raw.strip():
                    return raw.strip()
            if ct.tts_voice and str(ct.tts_voice).strip():
                return str(ct.tts_voice).strip()
            return None
    except Exception:
        logger.warning("[voice] post_id=%d 보이스 조회 실패", post_id, exc_info=True)
        return None


def _resolve_post_variant_config(post_id: int) -> dict:
    """게시글별 variant_config 조회 (contents.variant_config). 없으면 빈 dict.

    외부 연동(예: Again Spring 사연 ingest) 잡이 Content 생성 시 심어둔
    {source, external_id, video_gen, paired, outro_text, auto_hd_render} 등을 읽는다.
    """
    try:
        with SessionLocal() as db:
            ct = db.query(Content).filter_by(post_id=post_id).first()
            if ct and isinstance(ct.variant_config, dict):
                return ct.variant_config
    except Exception:
        logger.warning("[variant] post_id=%d variant_config 조회 실패", post_id, exc_info=True)
    return {}


def video_gen_enabled_for_post(post_id: int) -> bool:
    """게시글별 비디오 생성 활성화 여부.

    contents.variant_config.video_gen(bool)이 존재하면 그 값을 우선 적용하고,
    없으면 전역 설정 config.settings.VIDEO_GEN_ENABLED를 따른다.
    """
    from config.settings import VIDEO_GEN_ENABLED

    cfg = _resolve_post_variant_config(post_id)
    if "video_gen" in cfg:
        return bool(cfg["video_gen"])
    return VIDEO_GEN_ENABLED


def _resolve_post_outro_text(post_id: int) -> str | None:
    """게시글별 아웃트로 문구 오버라이드 (contents.variant_config.outro_text).

    설정돼 있으면 SceneDirector가 mood 기본 fixed_texts 중 random.choice()를
    건너뛰고 이 문구를 그대로 사용한다.
    """
    text = _resolve_post_variant_config(post_id).get("outro_text")
    return text if isinstance(text, str) and text.strip() else None


# ===========================================================================
# 에러 타입 정의
# ===========================================================================

class FailureType(Enum):
    """처리 실패 타입"""
    LLM_ERROR = "llm_error"              # LLM 요약 실패 (재시도 불가)
    TTS_ERROR = "tts_error"              # TTS 생성 실패 (재시도 가능)
    RENDER_ERROR = "render_error"        # 영상 렌더링 실패 (재시도 가능)
    NETWORK_ERROR = "network_error"      # 네트워크 오류 (재시도 가능)
    RESOURCE_ERROR = "resource_error"    # 리소스 부족 (VRAM 등, 재시도 가능)
    UNKNOWN_ERROR = "unknown_error"      # 알 수 없는 오류 (재시도 가능)


@dataclass
class RetryPolicy:
    """재시도 정책"""
    max_attempts: int = MAX_RETRY_COUNT   # 최대 시도 횟수
    backoff_factor: float = 2.0           # 백오프 배수
    initial_delay: float = 5.0            # 초기 대기 시간 (초)


# ===========================================================================
# Robust Processor
# ===========================================================================

class RobustProcessor:
    """견고한 게시글 처리기"""

    def __init__(self, retry_policy: Optional[RetryPolicy] = None):
        self.retry_policy = retry_policy or RetryPolicy()
        self.cfg = load_pipeline_config()
        self.gpu_manager = get_gpu_manager()

    async def process_with_retry(self, post: Post, session: Session) -> bool:
        """
        재시도 메커니즘을 포함한 게시글 처리

        Args:
            post: 처리할 게시글
            session: DB 세션

        Returns:
            성공 여부
        """
        attempt = 0
        last_error = None
        failure_type = None

        # 상태를 PROCESSING으로 변경
        post.status = PostStatus.PROCESSING
        post.retry_count = (post.retry_count or 0) + 1
        session.commit()
        logger.info(
            "처리 시작: post_id=%d title=%s (attempt=%d/%d)",
            post.id, post.title[:40], post.retry_count, self.retry_policy.max_attempts
        )

        # A/B 변형 배정 (첫 시도에서만 — retry_count=1)
        if (post.retry_count or 0) == 1:
            try:
                from analytics.ab_test import assign_variant
                assigned = assign_variant(post.id, session)
                if assigned:
                    session.commit()
                    logger.info(
                        "[A/B] 변형 배정: post_id=%d group=%s label=%s",
                        post.id, assigned["group_id"], assigned["label"],
                    )
            except Exception:
                logger.debug("A/B 변형 배정 실패 — 무시", exc_info=True)

        while attempt < self.retry_policy.max_attempts:
            try:
                # GPU 메모리 상태 로그
                self.gpu_manager.log_memory_status()

                # ===== Step 1: LLM 대본 생성 =====
                logger.info("[Step 1/3] LLM 대본 생성 중...")
                script = self._safe_generate_summary(post, session)
                logger.info("[Step 1/3] ✓ 대본 완료 (%d자)", len(script.to_plain_text()))

                # ===== Step 2: TTS 생성 =====
                logger.info("[Step 2/3] TTS 음성 생성 중...")
                _narration = (
                    script.to_narration_text()
                    if hasattr(script, "to_narration_text")
                    else script.to_plain_text()
                )
                with self.gpu_manager.managed_inference(ModelType.TTS, "tts_engine"):
                    audio_path = await self._safe_generate_tts(
                        _narration, post.id, post.site_code, post.origin_id
                    )
                logger.info("[Step 2/3] ✓ 음성 완료: %s", audio_path)

                # ===== Step 3: 렌더링 =====
                logger.info("[Step 3/3] 렌더링 중...")
                from ai_worker.renderer.layout import render_layout_video_from_scenes
                from ai_worker.scene.analyzer import analyze_resources
                from ai_worker.scene.director import SceneDirector
                from ai_worker.scene.validator import validate_and_fix

                _images: list[str] = post.images if isinstance(post.images, list) else []

                # Phase 1: 자원 분석
                _profile = analyze_resources(post, _images)
                logger.info(
                    "[Step 3/3] 전략=%s 이미지=%d",
                    _profile.strategy, _profile.image_count,
                )

                # Phase 3: 대본 검증/보정 (max_chars)
                _script_dict = validate_and_fix(
                    {"hook": script.hook, "body": list(script.body), "closer": script.closer}
                )

                # Phase 4: 씬 배분
                _db_cmts = sorted(
                    getattr(post, "comments", None) or [],
                    key=lambda c: getattr(c, "likes", 0) or 0,
                    reverse=True,
                )
                _director = SceneDirector(
                    _profile, _images, _script_dict, mood=script.mood,
                    post_id=post.id, comments=_db_cmts,
                    narrator_voice=script.narrator_voice or None,
                    chat_messages=script.chat_messages or None,
                    outro_text=_resolve_post_outro_text(post.id),
                    site_code=getattr(post, "site_code", None),
                    variant_config=_resolve_post_variant_config(post.id),
                )
                _scenes = _director.direct()
                logger.info("[Step 3/3] 씬=%d개", len(_scenes))

                # Phase 4.5-7: LTX-Video 클립 생성
                _scenes = await self._generate_video_clips(
                    _scenes, script, post.title or "", post.id
                )

                # Phase 5: 렌더링 — 통합 낭독 wav 재사용 (장면별 Fish Speech 생략)
                video_path = render_layout_video_from_scenes(
                    post,
                    _scenes,
                    narration_audio=audio_path if audio_path and Path(audio_path).exists() else None,
                )
                logger.info("[Step 3/3] ✓ 렌더링 완료: %s", video_path)

                # ===== Content 저장 (stale 객체 방지: 세션 갱신 후 re-fetch) =====
                _saved_post_id = post.id
                session.expire_all()
                post = session.query(Post).filter_by(id=_saved_post_id).first()
                if post is None:
                    raise ValueError(f"Post {_saved_post_id} 렌더링 완료 후 DB에서 사라짐 — 외부 삭제 가능성")
                self._save_content(post, session, script, audio_path, video_path)

                # ===== 썸네일 생성 (intro 프레임 우선 — Shorts thumbnails.set 소스) =====
                try:
                    from ai_worker.renderer.thumbnail import get_intro_thumbnail_path

                    images = post.images if isinstance(post.images, list) else []
                    intro_path = get_intro_thumbnail_path(post.site_code, post.origin_id)
                    if intro_path.is_file() and intro_path.stat().st_size > 1000:
                        thumb_path = intro_path
                        logger.info("intro 썸네일 사용: %s", thumb_path)
                    else:
                        thumb_path = get_thumbnail_path(post.site_code, post.origin_id)
                        generate_thumbnail(script.hook, images, thumb_path, style="waggle")
                    content = session.query(Content).filter(Content.post_id == post.id).first()
                    if content is not None:
                        upload_meta = dict(content.upload_meta or {})
                        upload_meta["thumbnail_path"] = str(thumb_path)
                        content.upload_meta = upload_meta
                        session.flush()
                        logger.info("썸네일 생성 완료: %s", thumb_path)
                except Exception:
                    logger.warning("썸네일 생성 실패 (비치명적)", exc_info=True)

                # ===== 성공 처리 =====
                post.status = PostStatus.PREVIEW_RENDERED
                session.commit()
                logger.info(
                    "✅ 처리 성공: post_id=%d → PREVIEW_RENDERED (attempts=%d)",
                    post.id, attempt + 1
                )
                return True

            except Exception as e:
                attempt += 1
                last_error = e
                failure_type = self._classify_error(e)

                # 에러 로깅
                logger.error(
                    "❌ 처리 실패: post_id=%d (attempt=%d/%d) error_type=%s",
                    post.id, attempt, self.retry_policy.max_attempts,
                    failure_type.value,
                    exc_info=True
                )

                # 에러 상세 로그
                self._log_failure(post.id, failure_type, str(e), attempt)

                # 재시도 불가능한 에러면 즉시 중단
                if failure_type == FailureType.LLM_ERROR:
                    logger.critical(
                        "🚫 재시도 불가: post_id=%d (LLM 에러 - 즉시 중단)",
                        post.id
                    )
                    break

                # 최대 시도 횟수 도달 전이면 재시도
                if attempt < self.retry_policy.max_attempts:
                    delay = self._calculate_backoff_delay(attempt)
                    logger.warning(
                        "🔄 재시도 대기: post_id=%d (%.1f초 후 재시도)",
                        post.id, delay
                    )
                    time.sleep(delay)
                    session.rollback()  # 트랜잭션 롤백
                else:
                    logger.error(
                        "⛔ 최대 재시도 초과: post_id=%d (attempts=%d)",
                        post.id, attempt
                    )

        # ===== 최종 실패 처리 =====
        self._mark_as_failed(post, session, failure_type, last_error, attempt)
        return False

    def _safe_generate_summary(self, post: Post, session: Session) -> ScriptData:
        """
        LLM 대본 생성. DB에 기존 JSON 대본이 있으면 재사용한다.

        Args:
            post: 게시글
            session: DB 세션

        Returns:
            ScriptData

        Raises:
            Exception: LLM 에러
        """
        try:
            # 기존 대본 확인 (편집실에서 저장된 JSON)
            existing = session.query(Content).filter(Content.post_id == post.id).first()
            if existing and existing.summary_text:
                try:
                    script = ScriptData.from_json(existing.summary_text)
                    if script.hook and len(script.hook) >= 5:
                        logger.info("[Step 1/3] 기존 대본 재사용 (LLM 스킵): post_id=%d", post.id)
                        return script
                except Exception:
                    logger.debug("기존 summary_text JSON 파싱 실패 — 새로 생성")

            # 베스트 댓글 추출
            best_comments = sorted(post.comments, key=lambda c: c.likes, reverse=True)[:5]
            comment_texts = [f"{c.author}: {c.content[:100]}" for c in best_comments]

            # 피드백 설정 + A/B 변형 지시 조립 (활성/레거시 경로 공통 helper)
            from analytics.feedback import build_extra_instructions
            extra_instructions: str | None = build_extra_instructions(post.id, session)

            # LLM 대본 생성 (post_id 전달 → LLM 이력 로그 연결)
            script = generate_script(
                title=post.title,
                body=post.content or "",
                comments=comment_texts,
                model=self.cfg.get("llm_model"),
                extra_instructions=extra_instructions,
                post_id=post.id,
            )

            # 유효성 검사
            plain = script.to_plain_text()
            if not plain or len(plain) < 10:
                raise ValueError("대본 텍스트가 너무 짧습니다")

            return script

        except Exception:
            logger.exception("LLM 대본 생성 실패")
            raise

    async def _safe_generate_tts(
        self,
        text: str,
        post_id: int,
        site_code: str,
        origin_id: str,
        voice_override: str | None = None,
    ) -> Path:
        """
        안전하게 TTS 음성 생성

        Args:
            text: 요약 텍스트
            post_id: 게시글 DB ID (캐시 로그용)
            site_code: 커뮤니티 코드
            origin_id: 원본 게시글 ID
            voice_override: 게시글별 보이스 오버라이드 (None → pipeline.json tts_voice 사용)

        Returns:
            음성 파일 경로

        Raises:
            Exception: TTS 에러
        """
        try:
            voice_id = voice_override or self.cfg.get("tts_voice", "default")

            audio_dir = MEDIA_DIR / "audio" / site_code
            audio_dir.mkdir(parents=True, exist_ok=True)
            audio_path = audio_dir / f"post_{origin_id}.{TTS_OUTPUT_FORMAT}"

            # TTS 캐시 확인 (동일 텍스트+목소리 → 재합성 스킵)
            tts_cache_dir = MEDIA_DIR / "tmp" / "tts_cache"
            tts_cache_dir.mkdir(parents=True, exist_ok=True)
            cache_hash = hashlib.md5(_tts_cache_key(voice_id, text).encode()).hexdigest()
            cached_audio = tts_cache_dir / f"{cache_hash}.{TTS_OUTPUT_FORMAT}"
            if cached_audio.exists():
                shutil.copy2(cached_audio, audio_path)
                logger.info("[TTS 캐시 히트] post_id=%d", post_id)
            else:
                # TTS 생성 (Fish Speech 직접 호출)
                await tts_synthesize(text=text, voice_key=voice_id, output_path=audio_path)
                shutil.copy2(audio_path, cached_audio)  # 캐시 저장

            # 파일 존재 확인
            if not audio_path.exists():
                raise FileNotFoundError(f"음성 파일 생성 실패: {audio_path}")

            # 파일 크기 확인 (최소 1KB)
            if audio_path.stat().st_size < 1024:
                raise ValueError(f"음성 파일이 너무 작습니다: {audio_path.stat().st_size} bytes")

            return audio_path

        except Exception as e:
            logger.exception("TTS 생성 실패")
            raise

    def _classify_error(self, error: Exception) -> FailureType:
        """
        에러 분류

        Args:
            error: 발생한 예외

        Returns:
            에러 타입
        """
        error_msg = str(error).lower()
        error_type = type(error).__name__.lower()

        # LLM 에러 (재시도 불가)
        if "ollama" in error_msg or "llm" in error_msg:
            return FailureType.LLM_ERROR

        # TTS 에러
        if "tts" in error_msg or "synthesize" in error_msg or "audio" in error_msg:
            return FailureType.TTS_ERROR

        # 렌더링 에러
        if "render" in error_msg or "video" in error_msg or "ffmpeg" in error_msg:
            return FailureType.RENDER_ERROR

        # 네트워크 에러
        if any(x in error_type for x in ["timeout", "connection", "network"]):
            return FailureType.NETWORK_ERROR

        # 리소스 에러 (VRAM, 디스크)
        if any(x in error_msg for x in ["memory", "vram", "cuda", "disk", "space"]):
            return FailureType.RESOURCE_ERROR

        # 기타
        return FailureType.UNKNOWN_ERROR

    def _calculate_backoff_delay(self, attempt: int) -> float:
        """
        Exponential Backoff 지연 시간 계산

        Args:
            attempt: 시도 횟수 (1부터 시작)

        Returns:
            대기 시간 (초)
        """
        return self.retry_policy.initial_delay * (self.retry_policy.backoff_factor ** (attempt - 1))

    def _log_failure(self, post_id: int, failure_type: FailureType, error_msg: str, attempt: int):
        """
        에러 로그 기록

        Args:
            post_id: 게시글 ID
            failure_type: 에러 타입
            error_msg: 에러 메시지
            attempt: 시도 횟수
        """
        log_file = MEDIA_DIR / "logs" / "failures.log"
        log_file.parent.mkdir(parents=True, exist_ok=True)

        with open(log_file, "a", encoding="utf-8") as f:
            timestamp = datetime.now().isoformat()
            f.write(
                f"{timestamp} | post_id={post_id} | "
                f"failure_type={failure_type.value} | "
                f"attempt={attempt} | "
                f"error={error_msg[:200]}\n"
            )

    def _save_content(
        self,
        post: Post,
        session: Session,
        script: ScriptData,
        audio_path: Path,
        video_path: Path
    ):
        """
        Content 레코드 저장

        Args:
            post: 게시글
            session: DB 세션
            script: 구조화 대본
            audio_path: 음성 파일 경로
            video_path: 영상 파일 경로
        """
        content = session.query(Content).filter(Content.post_id == post.id).first()
        if content is None:
            content = Content(post_id=post.id)
            session.add(content)

        content.summary_text = script.to_json()
        content.audio_path = str(audio_path)
        content.video_path = str(video_path)
        session.flush()

    def _mark_as_failed(
        self,
        post: Post,
        session: Session,
        failure_type: Optional[FailureType],
        last_error: Optional[Exception],
        attempts: int
    ):
        """
        게시글을 FAILED 상태로 마킹

        Args:
            post: 게시글
            session: DB 세션
            failure_type: 에러 타입
            last_error: 마지막 에러
            attempts: 시도 횟수
        """
        # stale 객체 방지: 장시간 작업 후 세션 갱신
        _post_id = post.id
        session.expire_all()
        post = session.query(Post).filter_by(id=_post_id).first()
        if post is None:
            logger.error("최종 실패 처리 불가: Post %d DB 없음", _post_id)
            return
        post.status = PostStatus.FAILED
        post.last_error = str(last_error)[:1000] if last_error else None
        session.commit()

        logger.error(
            "⛔ 최종 실패 처리: post_id=%d → FAILED | "
            "failure_type=%s | attempts=%d | error=%s",
            _post_id,
            failure_type.value if failure_type else "unknown",
            attempts,
            str(last_error)[:100] if last_error else "N/A"
        )

    # ===========================================================================
    # LTX-Video 클립 생성 (Phases 4.5-7)
    # ===========================================================================

    async def _generate_video_clips(
        self,
        scenes: list,
        script: ScriptData,
        post_title: str,
        post_id: int,
    ) -> list:
        """Phases 4.5-7: 비디오 모드 할당 → 프롬프트 생성 → 클립 생성.

        게시글별 video_gen_enabled_for_post() 결과가 False면 scenes를 그대로 반환한다
        (variant_config.video_gen 오버라이드 > 전역 VIDEO_GEN_ENABLED).
        """
        if not video_gen_enabled_for_post(post_id):
            logger.info("[video] video_gen 비활성 (post_id=%d) — 비디오 생성 스킵", post_id)
            return scenes

        import gc

        from ai_worker.scene.director import assign_video_modes
        from config.settings import VIDEO_I2V_THRESHOLD

        # Phase 4.5: video_mode 할당
        image_cache_dir = MEDIA_DIR / "tmp" / f"vid_image_cache_{post_id}"
        image_cache_dir.mkdir(parents=True, exist_ok=True)
        scenes = assign_video_modes(scenes, image_cache_dir, VIDEO_I2V_THRESHOLD)
        logger.info(
            "[video] Phase 4.5 완료: video_mode 할당 (%d씬)",
            sum(1 for s in scenes if getattr(s, "video_mode", None)),
        )

        # Phase 6: video prompt 생성 (LLM haiku 호출)
        stamp_progress(post_id, 6, "비디오 프롬프트")
        from ai_worker.video.prompt_engine import VideoPromptEngine

        prompt_engine = VideoPromptEngine()

        body_texts: list[str] = []
        for block in list(script.body):
            if isinstance(block, dict):
                body_texts.extend(block.get("lines", []))
            else:
                body_texts.append(str(block))
        body_summary = " ".join(body_texts)[:500]

        scenes = prompt_engine.generate_batch(
            scenes=scenes,
            mood=script.mood,
            title=post_title,
            body_summary=body_summary,
            post_id=post_id,
        )
        logger.info(
            "[video] Phase 6 완료: %d개 프롬프트 생성",
            sum(1 for s in scenes if getattr(s, "video_prompt", None)),
        )

        # ★ VRAM 정리: fish-speech 컨테이너 실제 정지 (2026-08-10, S2-pro 대응)
        #   S1-mini는 유휴 VRAM이 작아(~3-5GB) 로컬 캐시 정리+소프트 체크만으로
        #   충분했으나, S2-pro는 유휴 상태에서도 ~20GB를 점유해 컨테이너를
        #   실제로 내리지 않으면 ComfyUI GGUF UNet(~12.7GB) 로드가 OOM된다.
        #   (경위: .result/tts/failures-2026-08-09.md 실패 9)
        try:
            import torch
            torch.cuda.empty_cache()
        except Exception:
            pass
        gc.collect()

        from ai_worker.core.container_control import start_fish_speech, stop_fish_speech
        from ai_worker.core.gpu_manager import GPUMemoryManager

        stopped = await stop_fish_speech()
        if not stopped:
            logger.warning(
                "[video] fish-speech 정지 실패 — VRAM이 해제되지 않았을 수 있음",
            )

        _gm = self.gpu_manager
        _video_vram = _gm.MODEL_VRAM_REQUIREMENTS.get(ModelType.VIDEO, 12.0)
        _available = GPUMemoryManager.get_system_available_vram()
        if _available > 0 and _available < _video_vram:
            logger.warning(
                "[video] Phase 7: VRAM 부족 (available=%.1fGB < %.1fGB) — 긴급 정리",
                _available, _video_vram,
            )
            _gm.emergency_cleanup()
        else:
            logger.info("[video] Phase 7 진입 VRAM 확인: %.1fGB 여유", _available)

        try:
            # Phase 7: video clip 생성 (ComfyUI 경유)
            from ai_worker.video.comfy_client import ComfyUIClient
            from ai_worker.video.manager import VideoCheckpoint, VideoManager
            from config.settings import (
                VIDEO_GEN_TIMEOUT,
                VIDEO_GEN_TIMEOUT_DISTILLED,
                VIDEO_MAX_CLIPS_PER_POST,
                VIDEO_MAX_RETRY,
                VIDEO_NUM_FRAMES,
                VIDEO_NUM_FRAMES_FALLBACK,
                VIDEO_NUM_FRAMES_MAX,
                VIDEO_RESOLUTION,
                VIDEO_RESOLUTION_FALLBACK,
                VIDEO_STEPS,
                VIDEO_STEPS_DISTILLED,
                VIDEO_CFG,
                VIDEO_CFG_DISTILLED,
                VIDEO_FPS,
                VIDEO_WORKFLOW_MODE,
                get_comfyui_url,
            )

            logger.info("[video] Phase 7: 비디오 클립 생성 시작 (mode=%s)", VIDEO_WORKFLOW_MODE)

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

            # 체크포인트 로드
            checkpoint: VideoCheckpoint | None = None
            _checkpoint_state = load_render_checkpoint(post_id)
            if _checkpoint_state:
                try:
                    checkpoint = VideoCheckpoint.from_dict(_checkpoint_state)
                    logger.info(
                        "[video] 체크포인트 로드: post=%d, 완료=%d/%d씬",
                        post_id, len(checkpoint.video_scenes_done), checkpoint.total_scenes,
                    )
                except Exception:
                    logger.warning("[video] 체크포인트 파싱 실패 — 처음부터 시작", exc_info=True)
                    checkpoint = None

            # 씬 완료 콜백: DB에 즉시 체크포인트 커밋
            _done_scenes: list[int] = list(checkpoint.video_scenes_done) if checkpoint else []
            _done_clips: dict[str, str] = dict(checkpoint.video_clips) if checkpoint else {}

            stamp_progress(post_id, 7, "비디오 클립", scenes_done=0, total_scenes=len(scenes))

            def _on_scene_complete(scene_idx: int, clip_path: str) -> None:
                _done_scenes.append(scene_idx)
                _done_clips[str(scene_idx)] = clip_path
                checkpoint_dict = VideoCheckpoint(
                    phase=7, video_scenes_done=list(_done_scenes),
                    video_clips=dict(_done_clips), total_scenes=len(scenes),
                ).to_dict()
                save_render_checkpoint(post_id, checkpoint_dict)
                stamp_progress(post_id, 7, "비디오 클립", scenes_done=len(_done_scenes), total_scenes=len(scenes))

            scenes = await manager.generate_all_clips(
                scenes=scenes,
                mood=script.mood,
                post_id=post_id,
                title=post_title,
                body_summary=body_summary,
                checkpoint=checkpoint,
                on_scene_complete=_on_scene_complete,
            )

            # Phase 7 정상 완료 → 체크포인트 클리어 (progress 보존)
            try:
                clear_checkpoint_keep_progress(post_id)
            except Exception:
                logger.warning("[video] 체크포인트 클리어 실패 (비치명적)", exc_info=True)

            try:
                import torch
                torch.cuda.empty_cache()
            except Exception:
                pass
            gc.collect()

            video_ok = sum(1 for s in scenes if getattr(s, "video_clip_path", None))
            logger.info("[video] Phase 7 완료: 성공=%d, 최종 씬=%d", video_ok, len(scenes))

            return scenes
        finally:
            # ★ fish-speech 재기동 — Phase 7 성공/실패와 무관하게 항상 복구 시도
            #   (다음 LLM+TTS 요청이 이 컨테이너에 의존함)
            restarted = await start_fish_speech()
            if not restarted:
                logger.error(
                    "[video] fish-speech 재기동 실패 — 다음 TTS 요청이 실패할 수 있음. "
                    "수동 확인 필요: post_id=%d", post_id,
                )

    def _generate_video_clips_sync(
        self,
        scenes: list,
        script: ScriptData,
        post_title: str,
        post_id: int,
    ) -> list:
        """_generate_video_clips의 동기 래퍼 (render_stage 스레드 전용)."""
        import asyncio
        return asyncio.run(
            self._generate_video_clips(scenes, script, post_title, post_id)
        )

    # ===========================================================================
    # 파이프라인 분리 스테이지 (병렬 처리용)
    # ===========================================================================

    async def llm_tts_stage(self, post_id: int) -> tuple[ScriptData, Path]:
        """LLM 대본 생성 + TTS 합성 (CUDA/GPU 단계).

        파이프라인 병렬화에서 독립적으로 호출되는 1단계.
        완료 시 Content에 script/audio 중간 저장 후 (ScriptData, audio_path) 반환.
        """
        with SessionLocal() as session:
            post = session.query(Post).filter_by(id=post_id).first()
            if post is None:
                raise ValueError(f"Post {post_id} 없음")

            post.status = PostStatus.PROCESSING
            post.retry_count = (post.retry_count or 0) + 1
            post.last_error = None
            session.commit()
            logger.info("[Pipeline LLM+TTS] 시작: post_id=%d", post_id)
            stamp_progress(post_id, 1, "자원 분석")

            # A/B 테스트 변형 배정 (활성 테스트 있을 경우)
            try:
                from analytics.ab_test import assign_variant
                assign_variant(post_id, session)
                session.commit()
            except Exception:
                logger.debug("A/B 변형 배정 실패 — 무시", exc_info=True)

            use_cp = load_pipeline_config().get("use_content_processor") == "true"

            stamp_progress(post_id, 2, "대본 생성")
            if use_cp:
                # 5-Phase content_processor 파이프라인
                from ai_worker.script.chunker import chunk_with_llm
                from ai_worker.scene.analyzer import analyze_resources
                from analytics.feedback import build_extra_instructions

                _images: list[str] = post.images if isinstance(post.images, list) else []
                _profile = analyze_resources(post, _images)
                logger.info(
                    "[Pipeline LLM+TTS] content_processor 모드: 전략=%s 이미지=%d",
                    _profile.strategy, _profile.image_count,
                )
                # 와글봇 pipeline 기본 TTS만 사용 (성별/연령 pick_voice 금지 → 보이스 혼용 방지)
                # 우선순위: contents.tts_voice(외부 ingest) > pipeline.json tts_voice > VOICE_DEFAULT
                _narrator_voice = (
                    _resolve_post_voice(post_id)
                    or load_pipeline_config().get("tts_voice")
                    or VOICE_DEFAULT
                    or "default"
                )
                script = None
                _existing = session.query(Content).filter_by(post_id=post_id).first()
                if _existing and _existing.summary_text:
                    try:
                        _reuse = ScriptData.from_json(_existing.summary_text)
                        if _reuse.hook and len(_reuse.hook) >= 5 and _reuse.body:
                            _reuse.narrator_voice = _narrator_voice
                            if post.site_code == "again_spring":
                                _reuse.body = [
                                    b for b in _reuse.body
                                    if not (isinstance(b, dict) and b.get("type") == "comment")
                                ]
                            script = _reuse
                            logger.info(
                                "[Pipeline LLM+TTS] 기존 대본 재사용 (LLM 스킵) voice=%s post_id=%d",
                                _narrator_voice, post_id,
                            )
                    except Exception:
                        logger.debug("기존 summary 재사용 실패 — LLM 재생성", exc_info=True)
                        script = None
                if script is None and post.site_code == "again_spring" and _resolve_post_variant_config(post_id).get("pre_scripted") is True:
                    from ai_worker.scene.validator import smart_split_korean
                    chunks = smart_split_korean(" ".join((post.content or "").split()), max_chars=80)
                    script = ScriptData(
                        hook=(post.title or (chunks.pop(0) if chunks else "사연을 들려드릴게요"))[:80],
                        body=[{"line_count": 1, "lines": [chunk]} for chunk in chunks if chunk],
                        closer="", title_suggestion=post.title or "", tags=[], mood="daily",
                        narrator_voice=_narrator_voice,
                    )
                    logger.info("[Pipeline LLM+TTS] Again-Spring pre-scripted fast path post_id=%d", post_id)
                if script is None:
                    # 활성 경로에도 제목·베스트 댓글·피드백 지시 전달 (레거시 경로와 동일)
                    _best = sorted(post.comments, key=lambda c: c.likes, reverse=True)[:5]
                    _comment_texts = [f"{c.author}: {c.content[:100]}" for c in _best]
                    _extra = build_extra_instructions(post_id, session)
                    _raw = await chunk_with_llm(
                        post.content or "",
                        _profile,
                        post_id=post_id,
                        extended=True,
                        title=post.title,
                        best_comments=_comment_texts,
                        extra_instructions=_extra or "",
                    )
                    logger.info(
                        "[Pipeline LLM+TTS] narrator_voice=%s (pipeline tts_voice, ignore gender/age)",
                        _narrator_voice,
                    )
                    _chat_msgs = [
                        m for m in (_raw.get("chat_messages") or [])
                        if isinstance(m, dict) and m.get("text")
                    ]
                    _body = list(_raw.get("body", []))
                    # again_spring: 사연 본문에 섞인 LLM type=comment 제거 (DB 댓글 씬만 사용)
                    if post.site_code == "again_spring":
                        _body = [
                            b for b in _body
                            if not (isinstance(b, dict) and b.get("type") == "comment")
                        ]
                    script = ScriptData(
                        hook=_raw.get("hook", ""),
                        body=_body,
                        closer=_raw.get("closer", ""),
                        title_suggestion=_raw.get("title_suggestion", ""),
                        tags=_raw.get("tags", []),
                        mood=_raw.get("mood", "daily"),
                        narrator_voice=_narrator_voice,
                        chat_messages=_chat_msgs,
                    )
            else:
                # 레거시 generate_script 경로
                script = self._safe_generate_summary(post, session)

            _narration = script.to_narration_text() if hasattr(script, "to_narration_text") else script.to_plain_text()
            logger.info(
                "[Pipeline LLM+TTS] ✓ 대본 완료 (narration=%d자 plain=%d자)",
                len(_narration), len(script.to_plain_text()),
            )

            _post_voice = script.narrator_voice or _resolve_post_voice(post_id) or (
                load_pipeline_config().get("tts_voice") or VOICE_DEFAULT
            )
            stamp_progress(post_id, 5, "TTS 합성")
            with self.gpu_manager.managed_inference(ModelType.TTS, "tts_engine"):
                # hook+body만 통합 합성 — render가 장면별 재합성 없이 이 wav를 분할 사용
                audio_path = await self._safe_generate_tts(
                    _narration, post_id, post.site_code, post.origin_id,
                    voice_override=_post_voice,
                )
            _quality_cfg = _resolve_post_variant_config(post_id)
            from ai_worker.marketing.quality import MarketingQualityError, media_duration, requirements, shorten_script
            _requirements = requirements(post.site_code, _quality_cfg)
            _diagnostics: dict = {}
            if _requirements is not None:
                _initial_duration = media_duration(audio_path)
                _diagnostics = {"platform": _requirements.platform, "target_duration_sec": _requirements.target_sec, "allowed_duration_sec": _requirements.allowed_sec, "initial_tts_duration_sec": round(_initial_duration, 3), "tts_regenerated": False}
                if _initial_duration > _requirements.target_sec:
                    script, _before_chars, _after_chars = shorten_script(script, _initial_duration, _requirements.target_sec)
                    _narration = script.to_narration_text()
                    with self.gpu_manager.managed_inference(ModelType.TTS, "tts_engine"):
                        audio_path = await self._safe_generate_tts(_narration, post_id, post.site_code, post.origin_id, voice_override=_post_voice)
                    _final_tts_duration = media_duration(audio_path)
                    _diagnostics.update({"tts_regenerated": True, "script_chars_before": _before_chars, "script_chars_after": _after_chars, "final_tts_duration_sec": round(_final_tts_duration, 3)})
                    # TTS 중 별도 progress 세션이 contents를 갱신한다. 오래된 읽기
                    # 스냅샷을 버린 뒤 품질 진단을 저장해야 MariaDB errno 1020을 피한다.
                    session.rollback()
                    if _final_tts_duration > _requirements.allowed_sec:
                        _diagnostics["failure_code"] = "DURATION_TTS_EXCEEDED"
                        _save_generation_diagnostics(session, post_id, _diagnostics)
                        session.commit()
                        raise MarketingQualityError("DURATION_TTS_EXCEEDED", "shortened TTS exceeds allowed duration")
                else:
                    _diagnostics["final_tts_duration_sec"] = round(_initial_duration, 3)
                    # 위와 동일하게 장시간 TTS 뒤 최신 contents 스냅샷에서 저장한다.
                    session.rollback()
                _save_generation_diagnostics(session, post_id, _diagnostics)
                session.commit()
            stamp_progress(post_id, 5, "TTS 합성", done=True)
            logger.info("[Pipeline LLM+TTS] ✓ 음성 완료: %s", audio_path)

            # 장시간 LLM+TTS(수십 분) 동안 stamp_progress가 별도 세션으로 같은
            # contents 행을 갱신함 → MariaDB 11.6+ innodb_snapshot_isolation=ON에서
            # 오래된 REPEATABLE READ 스냅샷으로 UPDATE 시 errno 1020 발생.
            # render_stage(L903)와 동일하게 트랜잭션을 끝내고 새 스냅샷으로 저장.
            # (마지막 commit 이후 이 세션에 쓰기 없음 — rollback은 순수 트랜잭션 종료)
            session.rollback()

            # 중간 결과 저장 (렌더 단계에서 재사용)
            content = session.query(Content).filter_by(post_id=post_id).first()
            if content is None:
                content = Content(post_id=post_id)
                session.add(content)
            content.summary_text = script.to_json()
            content.audio_path = str(audio_path)
            # 사연 낭독 보이스를 contents.tts_voice에도 고정 (렌더 fallback=yohan 방지).
            # variant_config 음성(어드민/외부 ingest)이 있으면 그것을 최종 권위로 유지.
            _locked = _resolve_post_voice(post_id) or script.narrator_voice
            if _locked:
                content.tts_voice = _locked
                script.narrator_voice = _locked
            session.commit()

        return script, audio_path

    def render_stage(self, post_id: int, script: ScriptData, audio_path: Path) -> Path:
        """영상 렌더링 + 썸네일 생성 (CPU 단계).

        SceneDirector → render_layout_video_from_scenes()로 렌더링.
        파이프라인 병렬화에서 독립적으로 호출되는 2단계.
        완료 시 post.status → PREVIEW_RENDERED.
        """
        with SessionLocal() as session:
            post = session.query(Post).filter_by(id=post_id).first()
            if post is None:
                raise ValueError(f"Post {post_id} 없음")

            logger.info("[Pipeline Render] 시작: post_id=%d", post_id)

            from ai_worker.renderer.layout import render_layout_video_from_scenes
            from ai_worker.scene.analyzer import analyze_resources
            from ai_worker.scene.director import SceneDirector
            from ai_worker.scene.validator import validate_and_fix

            images: list[str] = post.images if isinstance(post.images, list) else []

            # Phase 1: 자원 분석
            profile = analyze_resources(post, images)
            logger.info(
                "[Pipeline Render] 전략=%s 이미지=%d",
                profile.strategy, profile.image_count,
            )

            # Phase 3: 대본 검증/보정 (max_chars)
            script_dict = validate_and_fix(
                {"hook": script.hook, "body": list(script.body), "closer": script.closer}
            )

            # Phase 4: 씬 배분
            stamp_progress(post_id, 4, "씬 구성")
            # stamp_progress()는 별도 세션에서 Content.pipeline_state를 갱신한다.
            # 기존 읽기 스냅샷을 끝내고 최신 행을 다시 읽어 deadline 상태 저장 시
            # MariaDB errno 1020 충돌이 나지 않게 한다.
            session.rollback()
            post = session.query(Post).filter_by(id=post_id).first()
            if post is None:
                raise ValueError(f"Post {post_id} 없음")
            _db_cmts2 = sorted(
                getattr(post, "comments", None) or [],
                key=lambda c: getattr(c, "likes", 0) or 0,
                reverse=True,
            )
            # 댓글 TTS 풀: variant_config(어드민 선택) → 없으면 pipeline.json
            _comment_voices = _resolve_post_comment_voices(post_id)
            director = SceneDirector(
                profile, images, script_dict, mood=script.mood,
                post_id=post_id, comments=_db_cmts2,
                narrator_voice=script.narrator_voice or None,
                chat_messages=script.chat_messages or None,
                outro_text=_resolve_post_outro_text(post_id),
                comment_voices=_comment_voices,
                site_code=getattr(post, "site_code", None),
                variant_config=_resolve_post_variant_config(post_id),
            )
            scenes = director.direct()
            _cfg = _resolve_post_variant_config(post_id)
            from ai_worker.marketing.quality import MarketingQualityError, media_duration, requirements
            _requirements = requirements(post.site_code, _cfg)
            if _requirements is not None:
                _applied_sibom = sum(1 for scene in scenes if getattr(scene, "sibom_role", None) and getattr(scene, "image_url", None))
                _diagnostics = dict(get_runtime_state(post_id, "generation_diagnostics") or {})
                _diagnostics.update({"sibom_plan_count": len(_cfg.get("sibom_plan") or _cfg.get("sibomPlan") or []), "sibom_applied_count": _applied_sibom, "sibom_required_count": _requirements.min_sibom})
                if _applied_sibom < _requirements.min_sibom:
                    _diagnostics["failure_code"] = "SIBOM_SCENES_TOO_SHORT"
                    _save_generation_diagnostics(session, post_id, _diagnostics)
                    session.commit()
                    raise MarketingQualityError("SIBOM_SCENES_TOO_SHORT", "not enough Sibomi images were applied")
                _save_generation_diagnostics(session, post_id, _diagnostics)
                session.commit()
            _deadline = _cfg.get("deadline_at")
            if _cfg.get("priority") == "MARKETING_CRITICAL" and isinstance(_deadline, str):
                try:
                    _due = datetime.fromisoformat(_deadline.replace("Z", "+00:00"))
                    _due = _due if _due.tzinfo else _due.replace(tzinfo=timezone.utc)
                    if datetime.now(timezone.utc) >= _due:
                        logger.info("[marketing] deadline reached; preserving configured comment count post_id=%d", post_id)
                except ValueError:
                    logger.warning("[marketing] invalid deadline_at post_id=%d", post_id)
            logger.info("[Pipeline Render] 씬=%d개", len(scenes))

            # 본문·intro·outro만 어드민 본문 보이스로 고정. 댓글/채팅은 풀에서 배정된 목소리 유지.
            _nv = _resolve_post_voice(post_id) or script.narrator_voice or None
            if not _nv:
                _nv = load_pipeline_config().get("tts_voice") or VOICE_DEFAULT
            if _nv:
                for _sc in scenes:
                    if getattr(_sc, "type", None) in ("comments", "chat"):
                        continue
                    _sc.voice_override = _nv
                logger.info(
                    "[Pipeline Render] narrator TTS locked=%s comment_pool=%s",
                    _nv, _comment_voices,
                )

            # Phase 4.5-7: LTX-Video 클립 생성
            scenes = self._generate_video_clips_sync(
                scenes, script, post.title or "", post_id
            )

            stamp_progress(post_id, 8, "FFmpeg 렌더링")
            _tts_cache = MEDIA_DIR / "tmp" / "tts_scene_cache" / str(post_id)
            _post_voice = _resolve_post_voice(post_id) or _nv
            video_path = render_layout_video_from_scenes(
                post, scenes,
                save_tts_cache=_tts_cache,
                voice_key=_post_voice,
                narration_audio=audio_path if audio_path and Path(audio_path).exists() else None,
            )

            # 렌더링 후 트랜잭션 갱신 ─ 장시간 렌더링(15분+) 중 대시보드가
            # contents 레코드를 수정하면 REPEATABLE READ 스냅샷이 오래되어
            # flush 시 MariaDB errno 1020 발생. rollback으로 오래된 트랜잭션을
            # 종료하고 최신 데이터로 새 트랜잭션 시작. (렌더링 전 DB 쓰기 없음)
            session.rollback()
            post = session.query(Post).filter_by(id=post_id).first()

            if _requirements is not None:
                _mp4_duration = media_duration(video_path)
                _diagnostics = dict(get_runtime_state(post_id, "generation_diagnostics") or {})
                _story_sec = float(_diagnostics.get("final_tts_duration_sec") or 0.0)
                _tail_sec = max(0.0, _mp4_duration - _story_sec)
                _outro_text_sec = 0.0
                from ai_worker.scene.analyzer import estimate_tts_duration
                for _scene in scenes:
                    if getattr(_scene, "type", None) == "outro":
                        _outro_text_sec += estimate_tts_duration(" ".join(str(x) for x in (getattr(_scene, "text_lines", None) or [])))
                _outro_sec = min(_tail_sec, _outro_text_sec)
                _diagnostics.update({
                    "story_duration_ms": round(_story_sec * 1000),
                    "comment_duration_ms": round(max(0.0, _tail_sec - _outro_sec) * 1000),
                    "outro_duration_ms": round(_outro_sec * 1000),
                    "final_duration_ms": round(_mp4_duration * 1000),
                    "final_mp4_duration_sec": round(_mp4_duration, 3),
                    "duration_source": "story_tts_ffprobe; final_mp4_ffprobe",
                })
                _save_generation_diagnostics(session, post_id, _diagnostics)
                session.commit()
            self._save_content(post, session, script, audio_path, video_path)
            logger.info("[Pipeline Render] ✓ 영상 완료: %s", video_path)

            # 썸네일 생성 (intro 프레임 우선 — Shorts thumbnails.set 소스)
            try:
                from ai_worker.renderer.thumbnail import get_intro_thumbnail_path

                images = post.images if isinstance(post.images, list) else []
                intro_path = get_intro_thumbnail_path(post.site_code, post.origin_id)
                if intro_path.is_file() and intro_path.stat().st_size > 1000:
                    thumb_path = intro_path
                    logger.info("intro 썸네일 사용: %s", thumb_path)
                else:
                    thumb_path = get_thumbnail_path(post.site_code, post.origin_id)
                    generate_thumbnail(script.hook, images, thumb_path, style="waggle")
                content = session.query(Content).filter_by(post_id=post_id).first()
                if content is not None:
                    upload_meta = dict(content.upload_meta or {})
                    upload_meta["thumbnail_path"] = str(thumb_path)
                    content.upload_meta = upload_meta
                    session.flush()
            except Exception:
                logger.warning("썸네일 생성 실패 (비치명적)", exc_info=True)

            post.status = PostStatus.PREVIEW_RENDERED
            session.commit()
            logger.info("[Pipeline Render] ✓ 완료: post_id=%d → PREVIEW_RENDERED", post_id)

        return video_path


# ===========================================================================
# 편의 함수
# ===========================================================================

async def process(post: Post, session: Session) -> None:
    """
    게시글 처리 (하위 호환성 유지)

    Args:
        post: 처리할 게시글
        session: DB 세션

    Raises:
        Exception: 처리 실패 시
    """
    processor = RobustProcessor()
    success = await processor.process_with_retry(post, session)
    if not success:
        raise RuntimeError(f"Post {post.id} processing failed after retries")
