"""ai_worker/renderer/_encode.py — FFmpeg 인코딩·세그먼트·concat 로직 (internal)"""

import logging
import subprocess
from pathlib import Path

from PIL import Image

logger = logging.getLogger(__name__)


def _resolve_codec() -> str:
    """h264_nvenc 반환 (RTX 3090 필수 환경)."""
    return "h264_nvenc"


def _get_encoder_args(codec: str) -> list[str]:
    return ["-c:v", "h264_nvenc", "-preset", "p4", "-cq", "23", "-pix_fmt", "yuv420p"]


def _escape_ffmpeg_text(text: str) -> str:
    """FFmpeg drawtext용 텍스트 이스케이프."""
    for ch in ("\\", "'", ":", ";", "%", "{", "}", '"'):
        text = text.replace(ch, f"\\{ch}")
    return text


def _build_layout_sfx_filter(
    plan: list[dict],
    timings: list[float],
    audio_dir: Path,
    layout: dict,
    tts_input_idx: int = 1,
    sfx_offset: float = -0.15,
) -> tuple[list[str], str]:
    """plan 씬 타입에 따른 효과음 amix 필터 구성."""
    # ── 당분간 SFX 사용 금지 (2026-03-04) ──
    tts_ref = f"[{tts_input_idx}:a]"
    return [], f"{tts_ref}acopy[aout]"
    # ── SFX 비활성화 끝 ──
    sfx_map: dict[str, str] = layout.get("layout_algorithm", {}).get("sfx", {
        "intro": "click.mp3",
        "image_text": "shutter.mp3",
        "text_only": "pop.mp3",
        "outro": "ding.mp3",
    })
    vol_map = {"click.mp3": 0.6, "shutter.mp3": 0.5, "pop.mp3": 0.45, "ding.mp3": 0.4}

    extra_inputs: list[str] = []
    filter_parts: list[str] = []
    sfx_labels: list[str] = []
    current_idx = tts_input_idx + 1

    for i, (entry, t_start) in enumerate(zip(plan, timings)):
        sfx_file = sfx_map.get(entry["type"], "pop.mp3")
        sfx_path = audio_dir / sfx_file
        if not sfx_path.exists():
            continue
        vol = vol_map.get(sfx_file, 0.4)
        delay_ms = max(0, int((t_start + sfx_offset) * 1000))
        label = f"sfx{i}"
        extra_inputs += ["-i", str(sfx_path)]
        filter_parts.append(f"[{current_idx}:a]adelay={delay_ms}|{delay_ms},volume={vol}[{label}]")
        sfx_labels.append(f"[{label}]")
        current_idx += 1

    tts_ref = f"[{tts_input_idx}:a]"
    if sfx_labels:
        all_refs = tts_ref + "".join(sfx_labels)
        n = 1 + len(sfx_labels)
        filter_str = ";".join(filter_parts) + f";{all_refs}amix=inputs={n}:normalize=0[aout]"
    else:
        filter_str = f"{tts_ref}acopy[aout]"

    return extra_inputs, filter_str


def _render_video_segment(
    base_frame: Image.Image,
    scene,
    text: str,
    duration: float,
    layout: dict,
    font_dir: Path,
    output_path: Path,
) -> Path:
    """비디오 클립을 base_frame 위에 합성하여 세그먼트 mp4로 생성한다.

    resize/loop 중간 파일 없이 단일 FFmpeg 명령으로 처리한다:
    - demux 레벨 -stream_loop으로 재인코딩 없는 루프
    - scale+crop+overlay를 filter_complex에 통합 → 인코딩 1회
    """
    from ai_worker.renderer._frames import _render_video_text_overlay

    va = layout["scenes"]["video_text"]["elements"]["video_area"]
    canvas_w = layout["canvas"]["width"]
    canvas_h = layout["canvas"]["height"]
    va_w = va["width"]
    va_h = va["height"]
    va_x = va["x"]
    va_y = va["y"]
    fps = 30
    frame_count = int(duration * fps)

    tmp_dir = output_path.parent
    base_png = tmp_dir / f"base_{output_path.stem}.png"
    base_frame.copy().save(str(base_png), "PNG")

    clip_path = Path(scene.video_clip_path)

    text_overlay_png = tmp_dir / f"txtoverlay_{output_path.stem}.png"
    _render_video_text_overlay(text, layout, font_dir, text_overlay_png)

    filter_complex = (
        f"[0:v]loop=loop={frame_count}:size=1:start=0,"
        f"setpts=N/{fps}/TB,fps={fps}[base];"
        f"[1:v]scale={va_w}:{va_h}:force_original_aspect_ratio=increase,"
        f"crop={va_w}:{va_h},fps={fps}[clip];"
        f"[base][clip]overlay={va_x}:{va_y}:shortest=0[vwith];"
        f"[2:v]scale={canvas_w}:{canvas_h}[txt];"
        f"[vwith][txt]overlay=0:0[vout]"
    )

    codec = _resolve_codec()
    enc_args = _get_encoder_args(codec)

    cmd = [
        "ffmpeg", "-y",
        "-i", str(base_png),
        "-stream_loop", "-1", "-i", str(clip_path),
        "-i", str(text_overlay_png),
        "-filter_complex", filter_complex,
        "-map", "[vout]",
        "-t", f"{duration:.3f}",
        *enc_args,
        "-r", str(fps),
        "-an",
        str(output_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        logger.error("[layout] video_segment 생성 실패:\n%s", result.stderr[-1000:])
        raise subprocess.CalledProcessError(result.returncode, cmd)

    base_png.unlink(missing_ok=True)
    text_overlay_png.unlink(missing_ok=True)

    logger.debug("[layout] video_segment 생성: %s (%.2fs)", output_path.name, duration)
    return output_path


def _render_static_segment(
    frame_png: Path,
    duration: float,
    output_path: Path,
) -> Path:
    """정적 PNG 프레임을 duration 길이의 mp4 세그먼트로 변환."""
    codec = _resolve_codec()
    enc_args = _get_encoder_args(codec)

    cmd = [
        "ffmpeg", "-y",
        "-loop", "1",
        "-i", str(frame_png),
        "-t", f"{duration:.3f}",
        *enc_args,
        "-r", "30",
        "-an",
        str(output_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        raise subprocess.CalledProcessError(result.returncode, cmd)

    return output_path
