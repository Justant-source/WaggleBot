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
    """인코더 인자. VRAM 여유가 없으면 CPU(libx264)로 폴백한다.

    fish-speech TTS가 24.6GB 중 23.9GB를 상주 점유한다. NVENC 세션 할당이
    실패하면 렌더가 통째로 죽고, 최악의 경우 TTS 컨테이너가 OOM으로 내려간다.
    여유 0.5GB 미만이면 느리더라도 CPU로 내려가는 편이 안전하다.
    """
    try:
        from ai_worker.core.gpu_manager import get_gpu_manager
        free_gb = get_gpu_manager().get_available_vram()
        if free_gb is not None and free_gb < 0.5:
            logger.warning("[encode] VRAM 여유 %.2fGB < 0.5GB — libx264 폴백", free_gb)
            return ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                    "-pix_fmt", "yuv420p"]
    except Exception:
        logger.debug("[encode] VRAM 조회 실패 — NVENC 유지", exc_info=True)
    return ["-c:v", "h264_nvenc", "-preset", "p4", "-cq", "23", "-pix_fmt", "yuv420p"]


def _escape_ffmpeg_text(text: str) -> str:
    """FFmpeg drawtext용 텍스트 이스케이프."""
    for ch in ("\\", "'", ":", ";", "%", "{", "}", '"'):
        text = text.replace(ch, f"\\{ch}")
    return text


def _resolve_sfx_path(sfx_file: str, audio_dir: Path) -> Path | None:
    """효과음 파일 경로를 찾는다.

    audio_dir는 TTS 음성 출력 폴더(assets/audio)라 효과음이 없다.
    효과음은 assets/sfx/<event>.wav에 승격돼 있으므로 그쪽을 먼저 본다.
    """
    if not sfx_file:
        return None
    candidates = []
    try:
        # 컨테이너에는 assets/media만 /app/media로 마운트된다 → 에셋도 그 아래에 둔다
        from config.settings import MEDIA_DIR
        candidates.append(Path(MEDIA_DIR) / "sfx" / sfx_file)
    except Exception:
        pass
    candidates.append(Path("/app/media/sfx") / sfx_file)
    candidates.append(audio_dir.parent / "sfx" / sfx_file)
    candidates.append(audio_dir / sfx_file)
    for c in candidates:
        try:
            if c.exists():
                return c
        except Exception:
            continue
    return None


def _build_layout_sfx_filter(
    plan: list[dict],
    timings: list[float],
    audio_dir: Path,
    layout: dict,
    tts_input_idx: int = 1,
    sfx_offset: float = -0.15,
    sfx_config: dict | None = None,
) -> tuple[list[str], str]:
    """
    director가 설정한 sfx_events 마커를 처리하여 효과음을 삽입한다.

    sfx_config: settings.yaml의 sfx.active 섹션 (이벤트 → {file, volume, offset})
    plan: 각 entry는 get("sfx_events", [])로 마커 리스트 포함 가능
    timings: 누적 초 리스트

    반환값: (extra_inputs 리스트, 최종 필터 문자열)
    """
    if sfx_config is None:
        sfx_config = {}

    tts_ref = f"[{tts_input_idx}:a]"

    # sfx_events 마커 수집 (최대 6개, 간격 규칙 적용)
    sfx_events_to_insert: list[tuple[str, float]] = []  # (event_key, timing_sec)
    last_sfx_time = -float('inf')
    min_gap = 2.5  # 기본 최소 간격

    for entry_idx, (entry, t_start) in enumerate(zip(plan, timings)):
        events = entry.get("sfx_events", [])
        if not events:
            continue

        for event_key in events:
            if len(sfx_events_to_insert) >= 6:  # 최대 6개 제한
                logger.info(
                    "[sfx] 영상당 최대 6회 초과, 해당 이벤트 dropped: %s @%.2fs",
                    event_key, t_start
                )
                continue

            # 간격 규칙: bubble 연속 시 1.0초, 나머지는 2.5초
            current_gap_rule = 1.0 if event_key == "bubble" and sfx_events_to_insert and sfx_events_to_insert[-1][0] == "bubble" else min_gap

            if t_start - last_sfx_time >= current_gap_rule or not sfx_events_to_insert:
                sfx_events_to_insert.append((event_key, t_start))
                last_sfx_time = t_start
            else:
                logger.debug(
                    "[sfx] 간격 규칙 위반, 이벤트 dropped: %s @%.2fs (last: %.2fs, gap: %.2fs < %.2fs)",
                    event_key, t_start, last_sfx_time, t_start - last_sfx_time, current_gap_rule
                )

    # SFX 필터 구성
    extra_inputs: list[str] = []
    filter_parts: list[str] = []
    sfx_labels: list[str] = []
    current_idx = tts_input_idx + 1

    for sfx_idx, (event_key, t_start) in enumerate(sfx_events_to_insert):
        event_cfg = sfx_config.get(event_key, {})
        sfx_file = event_cfg.get("file", "")
        sfx_vol = event_cfg.get("volume", 0.4)
        sfx_offset_sec = event_cfg.get("offset", 0.0)

        if not sfx_file:
            # 프로필 게이트로 설정이 비어 있는 경우(marketing_fast) — 정상이므로 조용히 건너뛴다
            continue
        sfx_path = _resolve_sfx_path(sfx_file, audio_dir)
        if sfx_path is None:
            logger.warning("[sfx] 파일 없음, skipped: %s", sfx_file)
            continue

        # 최종 타이밍: t_start + sfx_offset(전달된 인자, 대사 직전) + event_offset(이벤트별)
        delay_sec = t_start + sfx_offset + sfx_offset_sec
        delay_ms = max(0, int(delay_sec * 1000))

        label = f"sfx{sfx_idx}"
        extra_inputs += ["-i", str(sfx_path)]
        filter_parts.append(f"[{current_idx}:a]adelay={delay_ms}|{delay_ms},volume={sfx_vol}[{label}]")
        sfx_labels.append(f"[{label}]")
        current_idx += 1

    if sfx_labels:
        all_refs = tts_ref + "".join(sfx_labels)
        n = 1 + len(sfx_labels)
        filter_str = ";".join(filter_parts) + f";{all_refs}amix=inputs={n}:normalize=0[aout]"
        logger.info("[sfx] %d개 삽입됨 (최대 6개 규칙 준수)", len(sfx_labels))
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
    content_top: int = 0,
) -> Path:
    """비디오 클립을 base_frame 위에 합성하여 세그먼트 mp4로 생성한다.

    P3 (content_top > 0): 자연비율 contain 배치 — ffprobe로 클립 크기 측정 후
    scale=nw:nh (크롭 없음) + 중앙 overlay. 자막은 caption_above 위치(위쪽).

    P3 이전 (content_top == 0): 구 정사각 cover 방식 유지 (하위호환).

    resize/loop 중간 파일 없이 단일 FFmpeg 명령으로 처리한다:
    - demux 레벨 -stream_loop으로 재인코딩 없는 루프
    - scale+overlay를 filter_complex에 통합 → h264_nvenc 인코딩 1회 (ADR-0002)
    """
    import json as _json
    from ai_worker.renderer._frames import _render_video_text_overlay

    canvas_w = layout["canvas"]["width"]
    canvas_h = layout["canvas"]["height"]
    fps = 30
    frame_count = int(duration * fps)

    tmp_dir = output_path.parent
    base_png = tmp_dir / f"base_{output_path.stem}.png"
    base_frame.copy().save(str(base_png), "PNG")

    clip_path = Path(scene.video_clip_path)

    text_overlay_png = tmp_dir / f"txtoverlay_{output_path.stem}.png"
    _render_video_text_overlay(text, layout, font_dir, text_overlay_png,
                               content_top=content_top)

    if content_top > 0:
        # ── P3: 자연비율 contain ────────────────────────────────────────
        # ffprobe로 클립 원본 크기 측정
        probe_result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json",
             "-show_streams", "-select_streams", "v:0", str(clip_path)],
            capture_output=True, text=True, timeout=30,
        )
        clip_w, clip_h = 1280, 720  # 측정 실패 시 기본값
        if probe_result.returncode == 0:
            try:
                streams = _json.loads(probe_result.stdout).get("streams", [{}])
                clip_w = int(streams[0].get("width", 1280))
                clip_h = int(streams[0].get("height", 720))
            except Exception:
                pass

        va_new = layout["scenes"]["video_text"].get("video_area_new", {})
        media_max_w = va_new.get("max_width", 820)
        media_gap = va_new.get("gap_top", 50)

        # 자막 높이 추정 (최대 2줄 기준)
        cap_cfg = layout["scenes"]["video_text"].get("caption_above", {})
        cap_lh = cap_cfg.get("line_height", 62)
        cap_pad = cap_cfg.get("pad_top", 56)
        est_cap_h = cap_lh * 2  # 보수적 추정

        media_y = content_top + cap_pad + est_cap_h + media_gap
        media_max_h = max(100, canvas_h - media_y - 60)

        # contain 계산 (짝수 보정 필수 — h264 요구사항)
        scale = min(media_max_w / max(1, clip_w), media_max_h / max(1, clip_h))
        nw = max(2, int(clip_w * scale))
        nh = max(2, int(clip_h * scale))
        nw -= nw % 2
        nh -= nh % 2

        clip_x = (canvas_w - nw) // 2
        clip_y = media_y

        filter_complex = (
            f"[0:v]loop=loop={frame_count}:size=1:start=0,"
            f"setpts=N/{fps}/TB,fps={fps}[base];"
            f"[1:v]scale={nw}:{nh}:force_original_aspect_ratio=decrease,"
            f"fps={fps}[clip];"
            f"[base][clip]overlay={clip_x}:{clip_y}:shortest=0[vwith];"
            f"[2:v]scale={canvas_w}:{canvas_h}[txt];"
            f"[vwith][txt]overlay=0:0[vout]"
        )
        logger.debug(
            "[encode] P3 contain: clip=%dx%d → %dx%d @(%d,%d)",
            clip_w, clip_h, nw, nh, clip_x, clip_y,
        )
    else:
        # ── 구 방식: 정사각 cover ───────────────────────────────────────
        va = layout["scenes"]["video_text"]["elements"]["video_area"]
        va_w = va["width"]
        va_h = va["height"]
        va_x = va["x"]
        va_y = va["y"]

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
        "-vsync", "cfr",
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



def _concat_mp4_copy(a: Path, b: Path, output_path: Path) -> None:
    """두 mp4를 stream-copy concat (동일 코덱 전제)."""
    lst = output_path.with_suffix(".concat.txt")
    lst.write_text(
        f"file '{a.resolve()}'\nfile '{b.resolve()}'\n",
        encoding="utf-8",
    )
    try:
        result = subprocess.run(
            [
                "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                "-i", str(lst), "-c", "copy", str(output_path),
            ],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr[-500:] if result.stderr else "concat failed")
    finally:
        lst.unlink(missing_ok=True)


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
        "-vsync", "cfr",
        "-r", "30",
        "-an",
        str(output_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        raise subprocess.CalledProcessError(result.returncode, cmd)

    return output_path
