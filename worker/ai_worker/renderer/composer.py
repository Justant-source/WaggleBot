"""ai_worker/renderer/composer.py — 렌더링 진입점 (고화질/저화질 분기)"""

import logging
from pathlib import Path
from typing import Optional

from ai_worker.renderer.layout import render_layout_video_from_scenes, render_layout_video
from ai_worker.renderer.thumbnail import generate_thumbnail, get_thumbnail_path

logger = logging.getLogger(__name__)


def compose_video(
    post,
    scenes: list,
    *,
    output_path: Optional[Path] = None,
    tts_audio_cache: Optional[Path] = None,
    save_tts_cache: Optional[Path] = None,
) -> Path:
    """씬 목록 기반 최종 영상 렌더링.

    RTX 3090 GPU h264_nvenc 인코딩으로 1080×1920 영상을 생성한다.

    Args:
        post: Post DB 객체
        scenes: list[SceneDecision]
        output_path: 출력 경로 (None → 자동 생성)
        tts_audio_cache: TTS 캐시 로드 경로
        save_tts_cache: TTS 캐시 저장 경로
    Returns:
        렌더링된 mp4 파일 경로
    """
    return render_layout_video_from_scenes(
        post,
        scenes,
        output_path=output_path,
        tts_audio_cache=tts_audio_cache,
        save_tts_cache=save_tts_cache,
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
    script = ScriptData.from_json(content.summary_text) if content.summary_text else ScriptData(
        hook="", body=[], closer="", title_suggestion="", tags=[], mood="daily"
    )
    return render_layout_video(
        post,
        script,
        output_path=Path(output_path) if output_path else None,
        voice_key=voice_key,
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
