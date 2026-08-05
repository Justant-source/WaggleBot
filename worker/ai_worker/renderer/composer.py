"""ai_worker/renderer/composer.py — 렌더링 진입점 (고화질/저화질 분기)"""

import logging
from pathlib import Path
import subprocess
from typing import Optional

from ai_worker.renderer.layout import render_layout_video_from_scenes, render_layout_video
from ai_worker.renderer.thumbnail import generate_thumbnail, get_thumbnail_path

logger = logging.getLogger(__name__)


def _stream_remux_preview(source_path: Path, output_path: Path) -> bool:
    """Atomically remux an already-complete canonical preview into HD output.

    ``render_layout_video_from_scenes()`` already creates the full SceneDirector
    timeline (comments, closing timing, and aligned narration) at 1080x1920.
    Rebuilding that timeline later from ``ScriptData`` loses those scene-only
    entries.  Preserve the proven timeline with a stream-copy remux instead.
    """
    if source_path.resolve() == output_path.resolve():
        return False

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_name(f"{output_path.stem}.remux.tmp{output_path.suffix}")
    temporary_path.unlink(missing_ok=True)
    command = [
        "ffmpeg", "-y", "-i", str(source_path),
        "-map", "0", "-c", "copy", "-movflags", "+faststart",
        str(temporary_path),
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=600)
        if result.returncode != 0 or not temporary_path.exists() or temporary_path.stat().st_size < 1024:
            logger.warning(
                "[HD_RENDER] canonical preview remux failed: source=%s stderr=%s",
                source_path.name, (result.stderr or "")[-500:],
            )
            return False
        temporary_path.replace(output_path)
        logger.info(
            "[HD_RENDER] canonical SceneDirector preview remuxed: %s -> %s",
            source_path.name, output_path.name,
        )
        return True
    finally:
        temporary_path.unlink(missing_ok=True)


def compose_video(
    post,
    scenes: list,
    *,
    output_path: Optional[Path] = None,
    tts_audio_cache: Optional[Path] = None,
    save_tts_cache: Optional[Path] = None,
    narration_audio: Optional[Path] = None,
) -> Path:
    """씬 목록 기반 최종 영상 렌더링.

    RTX 3090 GPU h264_nvenc 인코딩으로 1080×1920 영상을 생성한다.

    Args:
        post: Post DB 객체
        scenes: list[SceneDecision]
        output_path: 출력 경로 (None → 자동 생성)
        tts_audio_cache: TTS 캐시 로드 경로
        save_tts_cache: TTS 캐시 저장 경로
        narration_audio: LLM+TTS 통합 낭독 wav (hook+body). 있으면 장면별 재합성 생략.
    Returns:
        렌더링된 mp4 파일 경로
    """
    return render_layout_video_from_scenes(
        post,
        scenes,
        output_path=output_path,
        tts_audio_cache=tts_audio_cache,
        save_tts_cache=save_tts_cache,
        narration_audio=narration_audio,
    )


def render_final_video(
    post,
    content,
    *,
    output_path: Optional[str | Path] = None,
    voice_key: Optional[str] = None,
) -> Path:
    """HD_RENDER 작업 핸들러용 진입점 — Content 객체에서 ScriptData를 복원해 렌더링한다.

    Args:
        post:        Post DB 객체
        content:     Content DB 객체 (summary_text에 ScriptData JSON 포함)
        output_path: 출력 경로 (None → 자동 생성)
        voice_key:   게시글별 TTS 보이스 키 (None → pipeline.json tts_voice 사용)
    Returns:
        렌더링된 mp4 파일 경로
    """
    from db.models import ScriptData
    from config.settings import MEDIA_DIR

    target_path = Path(output_path) if output_path else None
    preview_path = (
        Path(MEDIA_DIR) / "video" / post.site_code / f"post_{post.origin_id}_SD.mp4"
    )
    if target_path is not None and preview_path.exists() and preview_path.stat().st_size > 1024:
        if _stream_remux_preview(preview_path, target_path):
            return target_path

    script = ScriptData.from_json(content.summary_text) if content.summary_text else ScriptData(
        hook="", body=[], closer="", title_suggestion="", tags=[], mood="daily"
    )
    _narr = None
    if getattr(content, "audio_path", None):
        candidate = Path(content.audio_path)
        if candidate.exists() and candidate.stat().st_size > 1024:
            _narr = candidate
    return render_layout_video(
        post,
        script,
        output_path=target_path,
        voice_key=voice_key,
        narration_audio=_narr,
    )


def compose_thumbnail(
    hook_text: str,
    images: list[str],
    site_code: str,
    origin_id: str,
    *,
    style: str = "waggle",
) -> Path:
    """YouTube 썸네일 생성 (1280×720).

    Args:
        hook_text: 썸네일 표시 텍스트
        images: 배경 이미지 URL 목록
        site_code: 사이트 코드
        origin_id: 게시글 원본 ID
        style: 'waggle'(기본) | 'dramatic' | 'question' | 'funny' | 'news'
    Returns:
        생성된 JPG 파일 경로
    """
    output_path = get_thumbnail_path(site_code, origin_id)
    return generate_thumbnail(
        hook_text=hook_text,
        images=images,
        output_path=output_path,
        style=style,
    )
