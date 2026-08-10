"""레이아웃 렌더러 v2 — 베이스 프레임 베이킹 + 고정 Y좌표 슬롯.

씬 타입:
  intro     - 제목만 (title_only.svg)   → 베이스 프레임 그대로 사용
  image_text  - 이미지 + 텍스트 (image_text.svg)
  text_only - 텍스트만, 3슬롯 고정 Y (text_only.svg)
  outro     - 이미지만 (image_only.svg)   → 이미지가 남을 때 마지막 1프레임

핵심 설계:
  1. _create_base_frame() — base_layout.png + 제목을 헤더에 1회 합성
  2. 모든 씬 렌더러가 base_frame.copy()에서 시작 → 제목 위치 완전 고정
  3. text_only는 y_coords[] 배열로 슬롯별 Y좌표 명시 (동적 계산 없음)

배분 알고리즘:
  ratio = 이미지수 / 본문문장수
  ratio >= 0.8 → image_heavy : 거의 모든 문장에 이미지 사용
  ratio >= 0.3 → balanced  : 이미지 균등 분배
  ratio <  0.3 → text_heavy: text_only 위주, 앞에서 일부만 image_text
"""
import json
import logging
import shutil
import subprocess
import time
from pathlib import Path
from typing import Optional

from PIL import ImageFont

from config.settings import (
    ASSETS_DIR,
    MEDIA_DIR,
    TTS_TEXT_LEAD_SEC,
)

# ── 내부 모듈 re-import (기존 import 경로 호환) ──
from ai_worker.renderer._frames import (
    CANVAS_W, CANVAS_H, HEADER_H, HEADER_COLOR,
    _create_base_frame, _create_header_only_frame,
    _render_intro_frame, _render_image_text_frame,
    _render_text_only_frame, _render_image_only_frame,
    _render_outro_frame, _render_comments_frame,
    _render_video_text_overlay, _render_chat_frame, _wrap_korean, _draw_centered_text,
    _truncate, _fit_cover, _fit_contain, _paste_rounded, _load_image,
    _title_block_bottom_y, _fmt_count, _relative_time, _body_font_file,
    _create_breadcrumb_frame, _breadcrumb_bottom_y, _theme_name,
)
from ai_worker.renderer._tts import (
    _tts_chunk_async, _generate_tts_chunks, _merge_chunks,
    _get_audio_duration, _unpack_line, _INTRO_PAUSE_SEC,
)
from ai_worker.renderer._encode import (
    _render_video_segment, _render_static_segment,
    _resolve_codec, _get_encoder_args, _escape_ffmpeg_text,
    _build_layout_sfx_filter,
)

logger = logging.getLogger(__name__)

_LAYOUT_CONFIG: dict | None = None
_STATIC_CONCAT_CFR_ARGS: list[str] = ["-vsync", "cfr", "-r", "30"]
_STATIC_FINAL_FRAME_HOLD_FILTER: str = "tpad=stop_mode=clone:stop=-1"

# Again Spring(Tone L) 댓글 씬 — 레이아웃·낭독 모두 최대 3개로 고정(잠금된 제품 결정).
# 표시 상한은 config/layout.json의 themes.tone_l.scenes.comments.row.max_items에도
# 동일하게 반영되어 있다 — 여기서는 TTS/문장 생성 단계의 상한을 맞춘다.
_AGAIN_SPRING_MAX_COMMENTS = 3
# 댓글 점진 공개 시, 가장 최근 항목에 적용하는 페이드인 알파 단계(오름차순, 마지막 값
# 이전까지만 별도 프레임 — 최종 프레임은 항상 fade_alpha=1.0의 기존 프레임을 재사용한다).
_COMMENT_FADE_ALPHAS: tuple[float, ...] = (0.28, 0.58, 0.85)
_COMMENT_FADE_MAX_BUDGET_SEC = 0.30


# ---------------------------------------------------------------------------
# 설정 로더
# ---------------------------------------------------------------------------

def _load_layout() -> dict:
    global _LAYOUT_CONFIG
    if _LAYOUT_CONFIG is None:
        cfg_path = Path(__file__).resolve().parent.parent.parent / "config" / "layout.json"
        with open(cfg_path, encoding="utf-8") as f:
            _LAYOUT_CONFIG = json.load(f)
    return _LAYOUT_CONFIG


# ---------------------------------------------------------------------------
# 공통 유틸리티
# ---------------------------------------------------------------------------

def _deep_merge(base: dict, overrides: dict) -> dict:
    """overrides를 base에 재귀적으로 병합한다 (base를 in-place로 변경 후 반환).

    사이트별 테마 오버레이(예: themes.tone_l)를 기본 layout 위에 얹을 때 사용 —
    다른 사이트의 기본 global/scenes 딕셔너리는 건드리지 않는다(호출부에서 deepcopy 후 사용).
    """
    for k, v in overrides.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v
    return base


def _apply_vf_weight(font: ImageFont.FreeTypeFont, filename: str) -> None:
    """가변 폰트(Variable Font)의 굵기 축을 파일명에서 추론해 설정한다."""
    name_upper = Path(filename).stem.upper()
    if "BOLD" in name_upper:
        weight_name = "Bold"
    elif "MEDIUM" in name_upper:
        weight_name = "Medium"
    elif "LIGHT" in name_upper:
        weight_name = "Light"
    else:
        return
    try:
        font.set_variation_by_name(weight_name)
    except Exception:
        pass


def _load_font(font_dir: Path, filename: str, size: int) -> ImageFont.FreeTypeFont:
    """폰트 로드 (assets/fonts → 시스템 한글 → PIL 기본 폰트)."""
    font_path = font_dir / filename
    if font_path.exists():
        try:
            font = ImageFont.truetype(str(font_path), size)
            _apply_vf_weight(font, filename)
            return font
        except Exception:
            pass
    try:
        result = subprocess.run(
            ["fc-list", ":lang=ko", "--format=%{file}\n"],
            capture_output=True, text=True, timeout=5,
        )
        for line in result.stdout.splitlines():
            p = line.strip()
            if p and Path(p).exists():
                try:
                    font = ImageFont.truetype(p, size)
                    _apply_vf_weight(font, filename)
                    return font
                except Exception:
                    continue
    except Exception:
        pass
    logger.warning("폰트 없음: %s — PIL 기본 폰트 사용", filename)
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _run_async(coro) -> object:
    import asyncio
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result()
    return asyncio.run(coro)


def _text_lead_for_transition(following: dict, duration: float) -> float:
    """Return the visual lead for the following spoken frame.

    Audio timings remain untouched.  The preceding visual frame simply yields
    its last 100 ms to the next spoken line, so a viewer reads the line before
    its first syllable.  A silent decorative frame must not trigger a swap.
    """
    if following.get("sent_idx") is None or duration <= 0.001:
        return 0.0
    # Closing has an explicit contract in _apply_outro_timing(): prior visual
    # holds through the full 250 ms pause, then the closing text appears and
    # the WAV carries its own 150 ms lead. Borrowing here would make the text
    # appear during the preceding pause instead.
    if following.get("type") == "outro":
        return 0.0
    return min(TTS_TEXT_LEAD_SEC, max(duration - 0.001, 0.0))


def _build_visual_timeline(
    frame_paths: list[Path],
    plan: list[dict],
    durations: list[float],
    fade_frames: dict[int, list[Path]] | None = None,
) -> list[tuple[Path, float]]:
    """Build frame durations separately from the audio timeline.

    The returned timeline intentionally has no duplicate final frame. The
    static filter's ``tpad`` holds the final still until the audio-capped mux
    ends, avoiding the ffconcat terminal-entry edge case.

    fade_frames: optional {plan_index: [fade_step_path, ...]} — pre-rendered
    partial-opacity frames for a plan entry (e.g. a newly-revealed comment
    card fading in). Their combined duration is carved *out of* that entry's
    own current_duration (never added), so total per-index duration — and
    therefore audio/video sync — is unchanged. Used only by comments-scene
    entries on Again Spring (Tone L); everything else passes fade_frames=None
    and behaves exactly as before.
    """
    fade_frames = fade_frames or {}
    visual: list[tuple[Path, float]] = []
    for index, (frame_path, duration) in enumerate(zip(frame_paths, durations)):
        lead = 0.0
        if index + 1 < len(plan):
            lead = _text_lead_for_transition(plan[index + 1], duration)
        current_duration = duration - lead

        steps = fade_frames.get(index)
        if steps and current_duration > 0:
            budget = min(_COMMENT_FADE_MAX_BUDGET_SEC, current_duration * 0.5)
            step_dur = budget / len(steps)
            if step_dur >= 0.02:
                for step_path in steps:
                    visual.append((step_path, step_dur))
                current_duration -= budget

        if current_duration > 0:
            visual.append((frame_path, current_duration))
        if lead > 0:
            visual.append((frame_paths[index + 1], lead))
    return visual


def _append_text_only_line(
    history: list[dict],
    lines: list[str],
    block_type: str,
    max_slots: int,
) -> list[dict]:
    """Append one spoken line, resetting only after the third visible line."""
    if len(history) >= max_slots:
        history = []
    return [*history, {"lines": lines, "block_type": block_type}]


def _cap_output_to_audio(cmd: list[str], audio_duration: float) -> list[str]:
    """Add the final mux cap without changing the caller-owned command list."""
    return [*cmd[:-1], "-t", f"{audio_duration:.6f}", "-shortest", cmd[-1]]


def _build_static_concat_manifest(visual_timeline: list[tuple[Path, float]]) -> str:
    """Create an ffconcat manifest for a static timeline.

    FFconcat excludes a final-file duration. The static video filter therefore
    uses ``tpad=stop_mode=clone:stop=-1`` to hold that final still until the
    exact final mux cap; adding a terminal duplicate instead can be excluded
    by ``-t`` and make the video stream end at the previous frame.
    """
    lines: list[str] = []
    for frame_path, duration in visual_timeline:
        lines.append(f"file '{frame_path.resolve()}'\n")
        lines.append(f"duration {duration:.6f}\n")
    return "".join(lines)


# ---------------------------------------------------------------------------
# 배분 알고리즘
# ---------------------------------------------------------------------------

def _plan_sequence(
    sentences: list[dict],
    images: list[str],
    layout: dict,
) -> list[dict]:
    """이미지:텍스트 비율에 따라 씬 유형을 결정한다."""
    alg = layout.get("layout_algorithm", {})
    heavy_thr = alg.get("image_heavy_threshold", 0.8)
    mixed_thr = alg.get("image_mixed_threshold", 0.3)

    n_imgs = len(images)
    plan: list[dict] = []

    if not sentences:
        return plan

    plan.append({"type": "intro", "sent_idx": 0, "img_idx": None})

    body_sents = sentences[1:]
    n_body = len(body_sents)
    img_idx = 0

    if n_body == 0:
        if img_idx < n_imgs:
            plan.append({"type": "outro", "sent_idx": None, "img_idx": img_idx})
        return plan

    ratio = n_imgs / n_body

    if ratio >= heavy_thr:
        img_slots = set(range(n_body))
    elif ratio >= mixed_thr:
        if n_imgs > 0:
            step = n_body / n_imgs
            img_slots = {min(int(k * step), n_body - 1) for k in range(n_imgs)}
        else:
            img_slots = set()
    else:
        n_use = min(n_imgs, max(1, n_body // 4)) if n_imgs > 0 else 0
        img_slots = set(range(n_use))

    for local_i in range(n_body):
        sent_idx = local_i + 1
        if local_i in img_slots and img_idx < n_imgs:
            plan.append({"type": "image_text", "sent_idx": sent_idx, "img_idx": img_idx})
            img_idx += 1
        else:
            plan.append({"type": "text_only", "sent_idx": sent_idx, "img_idx": None})

    if img_idx < n_imgs:
        plan.append({"type": "outro", "sent_idx": None, "img_idx": img_idx})

    return plan


# ---------------------------------------------------------------------------
# SceneDecision 변환 유틸리티
# ---------------------------------------------------------------------------

def _scenes_to_plan_and_sentences(
    scenes: list,
    max_comment_items: int | None = None,
) -> tuple[list[dict], list[dict], list[str]]:
    """SceneDecision 목록을 내부 렌더러 형식 (sentences, plan, images)으로 변환한다.

    max_comment_items: comments 씬에서 사용할 최대 댓글 개수(낭독 TTS 포함 상한).
        None이면 상한 없음(기존 동작 유지, 와글 기본). Again Spring Tone L은
        레이아웃·낭독 모두 최대 3개로 고정한다(``_render_pipeline`` 호출부 참조).
    """
    sentences: list[dict] = []
    plan: list[dict] = []
    images: list[str] = []

    for scene_i, scene in enumerate(scenes):
        img_idx: Optional[int] = None
        if scene.image_url:
            img_idx = len(images)
            images.append(scene.image_url)

        if scene.type == "intro":
            text, audio = _unpack_line(scene.text_lines[0]) if scene.text_lines else ("", None)
            sent_idx = len(sentences)
            sentences.append({"text": text, "section": "hook", "audio": audio,
                              "voice_override": getattr(scene, "voice_override", None),
                              "tts_emotion": getattr(scene, "tts_emotion", "")})
            plan.append({"type": "intro", "sent_idx": sent_idx, "img_idx": img_idx, "scene_idx": scene_i})

        elif scene.type == "image_text":
            text, audio = _unpack_line(scene.text_lines[0]) if scene.text_lines else ("", None)
            sent_idx = len(sentences)
            sent_dict: dict = {
                "text": text, "section": "body", "audio": audio,
                "voice_override": scene.voice_override,
                "block_type": getattr(scene, "block_type", "body"),
                "author": getattr(scene, "author", None),
                "tts_emotion": getattr(scene, "tts_emotion", ""),
            }
            psl = getattr(scene, "pre_split_lines", None)
            if psl:
                sent_dict["lines"] = psl
            sentences.append(sent_dict)
            plan.append({"type": "image_text", "sent_idx": sent_idx, "img_idx": img_idx, "scene_idx": scene_i})

        elif scene.type == "video_text":
            # Pre-split editor lines are individual narration/display entries:
            # they must not appear as several new lines in a single frame.
            psl = getattr(scene, "pre_split_lines", None)
            source_lines = psl or scene.text_lines
            for line in source_lines:
                text, audio = _unpack_line(line)
                sent_idx = len(sentences)
                sent_dict = {
                    "text": text, "section": "body", "audio": audio,
                    "voice_override": scene.voice_override,
                    "block_type": getattr(scene, "block_type", "body"),
                    "author": getattr(scene, "author", None),
                    "tts_emotion": getattr(scene, "tts_emotion", ""),
                }
                sentences.append(sent_dict)
                # text_only와 동일한 렌더링이지만, scene_idx로 비디오 클립 연결
                plan.append({"type": "text_only", "sent_idx": sent_idx, "img_idx": None, "scene_idx": scene_i})

        elif scene.type == "text_only":
            psl = getattr(scene, "pre_split_lines", None)
            # A source block can contain up to three editor lines. Create one
            # timeline entry per line so the renderer reveals them in order.
            source_lines = psl or scene.text_lines
            for line in source_lines:
                text, audio = _unpack_line(line)
                sent_idx = len(sentences)
                sent_dict = {
                    "text": text, "section": "body", "audio": audio,
                    "voice_override": scene.voice_override,
                    "block_type": getattr(scene, "block_type", "body"),
                    "author": getattr(scene, "author", None),
                    "tts_emotion": getattr(scene, "tts_emotion", ""),
                }
                sentences.append(sent_dict)
                plan.append({"type": "text_only", "sent_idx": sent_idx, "img_idx": None, "scene_idx": scene_i})

        elif scene.type == "image_only":
            text, audio = _unpack_line(scene.text_lines[0]) if scene.text_lines else ("", None)
            sent_idx_val: Optional[int] = None
            if text:
                sent_idx_val = len(sentences)
                sentences.append({"text": text, "section": "body", "audio": audio, "voice_override": scene.voice_override,
                                  "tts_emotion": getattr(scene, "tts_emotion", "")})
            plan.append({"type": "image_only", "sent_idx": sent_idx_val, "img_idx": img_idx, "scene_idx": scene_i})

        elif scene.type == "outro":
            text, audio = _unpack_line(scene.text_lines[0]) if scene.text_lines else ("", None)
            sent_idx_val = None
            if text:
                sent_idx_val = len(sentences)
                sentences.append({"text": text, "section": "closer", "audio": audio,
                                  "voice_override": getattr(scene, "voice_override", None),
                                  "tts_emotion": getattr(scene, "tts_emotion", "")})
            plan.append({"type": "outro", "sent_idx": sent_idx_val, "img_idx": img_idx, "scene_idx": scene_i})

        elif scene.type == "comments":
            # 항목당 1개 TTS 엔트리 — text_only 패턴과 동일하게 점진적 낭독
            items = getattr(scene, "comment_items", None) or []
            if max_comment_items:
                items = items[:max_comment_items]
            for k, item in enumerate(items):
                content = (item.get("content") or "").strip()
                if not content:
                    # 빈 댓글 — TTS 엔트리 생략(0-dur 방지), item_idx(k)는 유지
                    continue
                sent_idx = len(sentences)
                sentences.append({
                    "text": content,
                    "section": "comment",
                    "audio": item.get("audio"),
                    "voice_override": item.get("voice"),
                    "block_type": "comment",
                    "author": item.get("author"),
                    "tts_emotion": "",
                })
                plan.append({
                    "type": "comments",
                    "sent_idx": sent_idx,
                    "img_idx": None,
                    "scene_idx": scene_i,
                    "item_idx": k,  # 0..k 누적 공개 인덱스 (전체 리스트 기준)
                })

        elif scene.type == "chat":
            # 항목당 1개 TTS 엔트리 — 시간 순서대로 점진적 낭독
            msgs = getattr(scene, "chat_messages", None) or []
            for k, msg in enumerate(msgs):
                text = (msg.get("text") or "").strip()
                if not text:
                    continue
                sent_idx = len(sentences)
                sentences.append({
                    "text": text,
                    "section": "body",
                    "audio": msg.get("audio"),
                    "voice_override": msg.get("voice"),
                    "block_type": "chat",
                    "author": msg.get("sender"),
                    "tts_emotion": "",
                })
                plan.append({
                    "type": "chat",
                    "sent_idx": sent_idx,
                    "img_idx": None,
                    "scene_idx": scene_i,
                    "item_idx": k,  # 0..k 누적 공개 인덱스
                })

    return sentences, plan, images


def _get_scene_for_entry(
    entry: dict,
    sentences: list[dict],
    scenes_list: list | None,
) -> object | None:
    """plan entry에 대응하는 SceneDecision을 찾는다."""
    if scenes_list is None:
        return None

    scene_idx = entry.get("scene_idx")
    if scene_idx is not None and 0 <= scene_idx < len(scenes_list):
        return scenes_list[scene_idx]

    sent_idx = entry.get("sent_idx")
    if sent_idx is None:
        return None

    target_text = sentences[sent_idx].get("text", "")
    if not target_text:
        return None

    for scene in scenes_list:
        for line in scene.text_lines:
            line_text = line.get("text", "") if isinstance(line, dict) else str(line)
            if line_text and line_text in target_text:
                return scene

    return None


# ---------------------------------------------------------------------------
# 공통 렌더링 파이프라인 (Steps 2 / 4 – 11)
# ---------------------------------------------------------------------------

def _render_pipeline(
    post_id: int,
    title: str,
    sentences: list[dict],
    plan: list[dict],
    images: list[str],
    output_path: Path,
    layout: dict,
    voice: str,
    rate: str,
    sfx_offset: float,
    max_slots: int,
    font_dir: Path,
    audio_dir: Path,
    save_tts_cache: Path | None = None,
    tts_audio_cache: Path | None = None,
    bgm_path: Path | None = None,
    scenes_list: list | None = None,
    meta: dict | None = None,
    narration_audio: Path | None = None,
    comments_fade_enabled: bool = False,
) -> Path:
    """sentences / plan / images 를 받아 mp4를 생성한다.

    comments_fade_enabled: True면 comments 씬의 각 신규 공개 항목에 짧은 페이드인
        서브프레임을 추가로 렌더한다(Again Spring Tone L 전용). 정적 concat 경로
        (비디오 클립이 섞이지 않은 일반적인 경우)에서만 적용되고, has_video_scenes
        하이브리드 경로에서는 기존처럼 즉시 표시된다(비디오 세그먼트는 frame_idx가
        plan/frame_paths와 1:1로 대응해야 하므로 서브프레임 확장을 적용하지 않음).
    """
    tmp_dir = MEDIA_DIR / "tmp" / f"layout_{post_id}"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    try:
        # ── Step 2: 베이스 프레임 베이킹 ──────────────────────
        # content_top: 제목블록 아래 콘텐츠 시작 Y (린치핀 — 모든 씬 공유)
        content_top = _title_block_bottom_y(layout, title, font_dir)
        base_frame = _create_base_frame(layout, title, font_dir, ASSETS_DIR, meta=meta)
        header_only_frame = _create_header_only_frame(layout, font_dir)

        # Tone L: body(image_text/text_only)/comments 씬은 큰 제목블록 대신
        # 가벼운 브레드크럼(칩+메타[+작은 제목]) 헤더를 쓴다 — content_top도 그만큼 짧다.
        # 와글(기본) 사이트는 _create_breadcrumb_frame/_breadcrumb_bottom_y가
        # 내부적으로 base_frame/content_top과 동일한 값을 반환하므로 동작 불변.
        if _theme_name(layout) == "tone_l":
            content_top_body = _breadcrumb_bottom_y(layout, title, font_dir, show_title=True)
            content_top_comments = _breadcrumb_bottom_y(layout, title, font_dir, show_title=False)
            breadcrumb_frame = _create_breadcrumb_frame(layout, title, font_dir, meta=meta, show_title=True)
            breadcrumb_frame_no_title = _create_breadcrumb_frame(layout, title, font_dir, meta=meta, show_title=False)
        else:
            content_top_body = content_top
            content_top_comments = content_top
            breadcrumb_frame = base_frame
            breadcrumb_frame_no_title = base_frame
        logger.info("[layout] 베이스 프레임 생성 완료 (content_top=%d)", content_top)

        # ── Step 4: 이미지 사전 다운로드 ──────────────────────
        # Tone L 메타포 이미지는 투명 PNG — surface(크림톤) 배경 위에 합성해야
        # 검정 배경 버그(알파 버림 시 투명영역 RGB가 그대로 검정으로 남는 문제)를 막는다.
        _img_bg_color = (
            layout.get("global", {}).get("palette", {}).get("surface", "#FFFFFF")
            if _theme_name(layout) == "tone_l" else "#FFFFFF"
        )
        image_cache: dict[int, Optional["Image.Image"]] = {}
        for entry in plan:
            img_idx = entry.get("img_idx")
            if img_idx is not None and img_idx not in image_cache:
                url = images[img_idx] if img_idx < len(images) else None
                image_cache[img_idx] = _load_image(url, tmp_dir, bg_color=_img_bg_color) if url else None

        # ── Steps 5~6: TTS 생성 또는 캐시 로드 ───────────────────
        merged_tts = tmp_dir / "merged_tts.wav"
        _cache_valid = False
        # 통합 낭독 wav를 쓰면 장면별 TTS 캐시는 무효 (이전 per-scene 캐시와 충돌)
        if narration_audio is not None:
            tts_audio_cache = None
        if tts_audio_cache and (tts_audio_cache / "durations.json").exists():
            try:
                durations: list[float] = json.loads(
                    (tts_audio_cache / "durations.json").read_text(encoding="utf-8")
                )
                cached_tts = tts_audio_cache / "merged_tts.wav"
                if cached_tts.exists() and cached_tts.stat().st_size > 0 and durations:
                    shutil.copy2(cached_tts, merged_tts)
                    total_dur = sum(durations)
                    logger.info("[layout] TTS 캐시 사용: post_id=%d (%d프레임, 총 %.1fs)",
                                post_id, len(durations), total_dur)
                    _cache_valid = True
                else:
                    logger.warning("[layout] TTS 캐시 불완전 — 재생성")
            except Exception as _e:
                logger.warning("[layout] TTS 캐시 로드 실패 (%s) — 재생성", _e)
        if not _cache_valid:
            logger.info("[layout] TTS 생성 시작")
            from ai_worker.tts.fish_client import _warmup_model
            _run_async(_warmup_model())
            t0 = time.time()
            durations = _run_async(
                _generate_tts_chunks(
                    plan, sentences, tmp_dir, voice, rate,
                    narration_audio=narration_audio,
                )
            )
            total_dur = sum(durations)
            logger.info("[layout] TTS 완료: %d프레임, 총 %.1fs (%.2fs)",
                        len(durations), total_dur, time.time() - t0)

            chunk_paths = [tmp_dir / f"chunk_{i:03d}.wav" for i in range(len(plan))]
            _merge_chunks(
                chunk_paths, merged_tts,
                skip_global_loudnorm=(narration_audio is not None),
            )

            if save_tts_cache:
                save_tts_cache.mkdir(parents=True, exist_ok=True)
                shutil.copy2(merged_tts, save_tts_cache / "merged_tts.wav")
                (save_tts_cache / "durations.json").write_text(
                    json.dumps(durations), encoding="utf-8"
                )
                logger.info("[layout] TTS 캐시 저장: %s", save_tts_cache)

        # 0-duration 프레임 제거 — TTS 실패 프레임이 concat에서 빈 세그먼트로 이어지는 것 방지
        if any(d <= 0.0 for d in durations):
            _zero_count = sum(1 for d in durations if d <= 0.0)
            logger.warning("[layout] TTS 실패 프레임 %d개 제거 (dur=0)", _zero_count)
            _pairs = [(p, d) for p, d in zip(plan, durations) if d > 0.0]
            if _pairs:
                plan, durations = [list(x) for x in zip(*_pairs)]
            else:
                raise RuntimeError("모든 TTS 프레임 실패 — 렌더링 불가")

        # ── Step 7: text_only용 줄바꿈 사전 계산 ──────────────
        sc_to = layout["scenes"]["text_only"]
        to_ta = sc_to["elements"]["text_area"]
        # 실제 렌더 폰트와 동일 기준으로 줄바꿈 계산 (테마별 분기: 와글=Bold 산세리프 / Tone L=세리프)
        to_font = _load_font(font_dir, _body_font_file(layout), to_ta["font_size"])
        to_max_w = to_ta["max_width"]
        to_max_chars = sc_to.get("text_max_chars", 0)

        for sent in sentences:
            if "lines" in sent:
                expanded: list[str] = []
                for line in sent["lines"]:
                    expanded.extend(_wrap_korean(line, to_font, to_max_w))
                sent["lines"] = expanded
                continue
            sent["lines"] = _wrap_korean(sent["text"], to_font, to_max_w)

        # ── Step 8: PIL 프레임 생성 ────────────────────────────
        logger.info("[layout] 프레임 생성 시작")
        t1 = time.time()
        frame_paths: list[Path] = []
        text_only_history: list[dict] = []
        comment_fade_frames: dict[int, list[Path]] = {}

        for frame_idx, entry in enumerate(plan):
            scene_type = entry["type"]
            sent_idx = entry.get("sent_idx")
            img_idx = entry.get("img_idx")
            frame_path = tmp_dir / f"frame_{frame_idx:03d}.png"

            if scene_type != "text_only":
                text_only_history = []

            if scene_type == "intro":
                img_pil = image_cache.get(img_idx) if img_idx is not None else None
                hook_text = sentences[sent_idx]["text"] if sent_idx is not None else ""
                _render_intro_frame(
                    base_frame, img_pil, hook_text,
                    layout, font_dir, frame_path, content_top, stage=1,
                )

            elif scene_type == "image_text":
                img_pil = image_cache.get(img_idx) if img_idx is not None else None
                text = sentences[sent_idx]["text"] if sent_idx is not None else ""
                if img_pil is None:
                    logger.warning("[layout] 프레임 %d: image_text→text_only 폴백 (이미지 없음)", frame_idx)
                    lines = sentences[sent_idx].get("lines", [text]) if sent_idx is not None else [text]
                    fallback_entry = {"lines": lines,
                                      "block_type": entry.get("block_type", "body")}
                    _render_text_only_frame(
                        breadcrumb_frame, [fallback_entry], layout, font_dir, frame_path,
                        content_top_body, stage=2,
                    )
                else:
                    _render_image_text_frame(
                        breadcrumb_frame, img_pil, text, layout, font_dir, frame_path,
                        content_top_body, stage=2,
                    )

            elif scene_type == "text_only":
                # v3: 이전 슬롯 흐림(greying) 제거 — 전 슬롯 동일 검정
                new_lines = sentences[sent_idx]["lines"] if sent_idx is not None else []

                if len(text_only_history) >= max_slots:
                    if len(new_lines) > max_slots:
                        logger.warning("[layout] 프레임 %d: %d줄 초과 — 단독 표시",
                                       frame_idx, len(new_lines))

                sent_data = sentences[sent_idx] if sent_idx is not None else {}
                text_only_history = _append_text_only_line(
                    text_only_history,
                    new_lines,
                    sent_data.get("block_type", "body"),
                    max_slots,
                )
                _render_text_only_frame(
                    breadcrumb_frame, text_only_history, layout, font_dir, frame_path,
                    content_top_body, stage=2,
                )

            elif scene_type == "image_only":
                img_pil = image_cache.get(img_idx) if img_idx is not None else None
                _render_image_only_frame(
                    base_frame, img_pil, layout, frame_path, content_top,
                )

            elif scene_type == "outro":
                # 아웃트로는 헤더only 프레임 사용 (제목블록 없음)
                outro_text = sentences[sent_idx]["text"] if sent_idx is not None else ""
                _render_outro_frame(
                    header_only_frame, outro_text, layout, font_dir, frame_path,
                )

            elif scene_type == "comments":
                # 댓글 씬: SceneDecision에서 comment_items 추출, reveal_count로 누적 공개
                scene = _get_scene_for_entry(entry, sentences, scenes_list)
                items = getattr(scene, "comment_items", None) if scene else None
                reveal = entry.get("item_idx")
                reveal_count = (reveal + 1) if reveal is not None else None
                _render_comments_frame(
                    breadcrumb_frame_no_title, items or [], layout, font_dir, frame_path,
                    content_top_comments,
                    reveal_count=reveal_count, stage=3,
                )
                # Tone L: 새로 드러난 카드가 즉시 나타나지 않고 짧게 페이드인하도록
                # 낮은 alpha의 서브프레임을 미리 렌더한다 (정적 concat 경로 전용 —
                # _build_visual_timeline이 이 프레임들의 지속시간을 본 프레임의
                # current_duration에서 그대로 떼어 쓰므로 오디오 타이밍은 불변).
                if comments_fade_enabled and reveal_count is not None:
                    fade_paths: list[Path] = []
                    for step_i, alpha in enumerate(_COMMENT_FADE_ALPHAS):
                        fade_path = tmp_dir / f"frame_{frame_idx:03d}_cfade{step_i}.png"
                        _render_comments_frame(
                            breadcrumb_frame_no_title, items or [], layout, font_dir, fade_path,
                            content_top_comments,
                            reveal_count=reveal_count, fade_alpha=alpha, stage=3,
                        )
                        fade_paths.append(fade_path)
                    comment_fade_frames[frame_idx] = fade_paths

            elif scene_type == "chat":
                # 채팅 버블 씬: SceneDecision에서 chat_messages 추출, reveal_count로 누적 공개
                scene = _get_scene_for_entry(entry, sentences, scenes_list)
                msgs = getattr(scene, "chat_messages", None) if scene else None
                reveal = entry.get("item_idx")
                _render_chat_frame(
                    base_frame, msgs or [], layout, font_dir, frame_path, content_top,
                    reveal_count=(reveal + 1) if reveal is not None else None,
                )

            frame_paths.append(frame_path)

        logger.info("[layout] 프레임 %d장 완료 (%.2fs)", len(frame_paths), time.time() - t1)

        # 비디오 씬 존재 여부 확인
        has_video_scenes = False
        if scenes_list:
            has_video_scenes = any(
                getattr(s, "video_clip_path", None)
                and not getattr(s, "video_generation_failed", False)
                for s in scenes_list
            )

        if has_video_scenes:
            # ── Step 8.5: 하이브리드 세그먼트 생성 ─────────────────
            logger.info("[layout] 하이브리드 렌더링: 비디오 씬 포함")
            segment_paths: list[Path] = []
            visual_segments: list[tuple[int, float]] = []
            for frame_idx, dur in enumerate(durations):
                lead = 0.0
                if frame_idx + 1 < len(plan):
                    lead = _text_lead_for_transition(plan[frame_idx + 1], dur)
                if dur - lead > 0:
                    visual_segments.append((frame_idx, dur - lead))
                if lead > 0:
                    visual_segments.append((frame_idx + 1, lead))

            for segment_idx, (frame_idx, dur) in enumerate(visual_segments):
                entry = plan[frame_idx]
                segment_path = tmp_dir / f"seg_{segment_idx:03d}.mp4"
                scene = _get_scene_for_entry(entry, sentences, scenes_list)

                if (
                    scene is not None
                    and getattr(scene, "video_clip_path", None)
                    and not getattr(scene, "video_generation_failed", False)
                ):
                    text = sentences[entry["sent_idx"]]["text"] if entry.get("sent_idx") is not None else ""
                    try:
                        _render_video_segment(
                            base_frame=base_frame,
                            scene=scene,
                            text=text,
                            duration=dur,
                            layout=layout,
                            font_dir=font_dir,
                            output_path=segment_path,
                            content_top=content_top,
                        )
                    except Exception as e:
                        logger.warning(
                            "[layout] 비디오 세그먼트 %d 생성 실패, 정적 폴백: %s",
                            frame_idx, e,
                        )
                        _render_static_segment(frame_paths[frame_idx], dur, segment_path)
                else:
                    _render_static_segment(frame_paths[frame_idx], dur, segment_path)

                segment_paths.append(segment_path)

            # ── Step 9: segment concat ─────────────────────────────
            concat_file = tmp_dir / "concat_list.txt"
            concat_lines_list: list[str] = []
            for sp in segment_paths:
                concat_lines_list.append(f"file '{sp.resolve()}'\n")
            concat_file.write_text("".join(concat_lines_list), encoding="utf-8")

            video_only = tmp_dir / "video_only.mp4"
            concat_cmd = [
                "ffmpeg", "-y",
                "-f", "concat", "-safe", "0",
                "-i", str(concat_file),
                "-c", "copy",
                str(video_only),
            ]
            concat_result = subprocess.run(concat_cmd, capture_output=True, text=True, timeout=300)
            if concat_result.returncode != 0:
                logger.error("[layout] concat 실패:\n%s", concat_result.stderr[-2000:])
                raise subprocess.CalledProcessError(concat_result.returncode, concat_cmd)

            # concat 완료 후 세그먼트 파일 즉시 삭제 (디스크 절약)
            for seg_path in segment_paths:
                seg_path.unlink(missing_ok=True)
            logger.debug("[layout] seg_*.mp4 %d개 즉시 삭제 완료", len(segment_paths))

            # ── Step 10–11: 오디오 합성 ────────────────────────────
            timings: list[float] = []
            acc = 0.0
            for dur in durations:
                timings.append(acc)
                acc += dur

            extra_inputs, sfx_filter = _build_layout_sfx_filter(
                plan, timings, audio_dir, layout,
                tts_input_idx=1, sfx_offset=sfx_offset,
            )

            effective_bgm: Path | None = None
            if bgm_path is not None and Path(bgm_path).exists():
                effective_bgm = Path(bgm_path)
                logger.info("[layout] BGM 사용 (bgm_path): %s", effective_bgm.name)
            elif bgm_path is not None:
                logger.warning("[layout] bgm_path 파일 없음: %s — BGM 없이 인코딩", bgm_path)

            if effective_bgm is not None:
                bgm_audio_filter = (
                    f"[1:a]anull[tts_pad];"
                    f"[2:a]volume=0.15,aloop=loop=-1:size=2e+09[bgm_loop];"
                    f"[tts_pad][bgm_loop]amix=inputs=2:duration=first:normalize=0[aout]"
                )
                cmd = [
                    "ffmpeg", "-y",
                    "-i", str(video_only),
                    "-i", str(merged_tts),
                    "-stream_loop", "-1", "-i", str(effective_bgm),
                    "-filter_complex", bgm_audio_filter,
                    "-map", "0:v", "-map", "[aout]",
                    "-c:v", "copy",
                    "-c:a", "aac", "-b:a", "192k",
                    str(output_path),
                ]
            else:
                cmd = [
                    "ffmpeg", "-y",
                    "-i", str(video_only),
                    "-i", str(merged_tts),
                    *extra_inputs,
                    "-filter_complex", sfx_filter,
                    "-map", "0:v", "-map", "[aout]",
                    "-c:v", "copy",
                    "-c:a", "aac", "-b:a", "192k",
                    str(output_path),
                ]
        else:
            # ── Step 9 (기존): 정적 PNG concat ─────────────────────
            concat_file = tmp_dir / "concat_list.txt"
            # Audio durations and frame durations are independent: each next
            # spoken line borrows its first 100 ms from the preceding visual.
            visual_timeline = _build_visual_timeline(
                frame_paths, plan, durations, fade_frames=comment_fade_frames,
            )
            concat_file.write_text(
                _build_static_concat_manifest(visual_timeline), encoding="utf-8",
            )
            logger.info("[layout] text visual lead=%.2fs (audio unchanged)", TTS_TEXT_LEAD_SEC)

            # ── Step 10: 타임스탬프 + SFX ──────────────────────────
            timings = []
            acc = 0.0
            for dur in durations:
                timings.append(acc)
                acc += dur

            extra_inputs, sfx_filter = _build_layout_sfx_filter(
                plan, timings, audio_dir, layout,
                tts_input_idx=1, sfx_offset=sfx_offset,
            )

            # ── Step 11: FFmpeg 인코딩 ─────────────────────────────
            codec = _resolve_codec()
            enc_args = _get_encoder_args(codec)
            video_filter = (
                "[0:v]scale=1080:1920:force_original_aspect_ratio=decrease,"
                "pad=1080:1920:(ow-iw)/2:(oh-ih)/2,"
                f"{_STATIC_FINAL_FRAME_HOLD_FILTER}[vout]"
            )

            effective_bgm = None
            if bgm_path is not None and Path(bgm_path).exists():
                effective_bgm = Path(bgm_path)
                logger.info("[layout] BGM 사용 (bgm_path): %s", effective_bgm.name)
            elif bgm_path is not None:
                logger.warning("[layout] bgm_path 파일 없음: %s — BGM 없이 인코딩", bgm_path)

            if effective_bgm is not None:
                bgm_sfx_extra, bgm_sfx_filter = _build_layout_sfx_filter(
                    plan, timings, audio_dir, layout,
                    tts_input_idx=1, sfx_offset=sfx_offset,
                )
                bgm_audio_filter = (
                    f"[1:a]anull[tts_pad];"
                    f"[2:a]volume=0.15,aloop=loop=-1:size=2e+09[bgm_loop];"
                    f"[tts_pad][bgm_loop]amix=inputs=2:duration=first:normalize=0[aout_premix]"
                )
                if bgm_sfx_extra:
                    bgm_extra_sfx, bgm_sfx_str = _build_layout_sfx_filter(
                        plan, timings, audio_dir, layout,
                        tts_input_idx=1, sfx_offset=sfx_offset,
                    )
                    bgm_sfx_str_patched = bgm_sfx_str.replace(
                        f"[1:a]acopy[aout]", "[aout_premix]acopy[aout]"
                    ).replace(
                        f"[1:a]", "[aout_premix]"
                    )
                    filter_complex = f"{video_filter};{bgm_audio_filter};{bgm_sfx_str_patched}"
                    cmd = [
                        "ffmpeg", "-y",
                        "-f", "concat", "-safe", "0", "-i", str(concat_file),
                        "-i", str(merged_tts),
                        "-stream_loop", "-1", "-i", str(effective_bgm),
                        *bgm_extra_sfx,
                        "-filter_complex", filter_complex,
                        "-map", "[vout]", "-map", "[aout]",
                        *enc_args,
                        "-c:a", "aac", "-b:a", "192k", *_STATIC_CONCAT_CFR_ARGS,
                        str(output_path),
                    ]
                else:
                    bgm_audio_filter_final = bgm_audio_filter.replace(
                        "[aout_premix]", "[aout]"
                    )
                    filter_complex = f"{video_filter};{bgm_audio_filter_final}"
                    cmd = [
                        "ffmpeg", "-y",
                        "-f", "concat", "-safe", "0", "-i", str(concat_file),
                        "-i", str(merged_tts),
                        "-stream_loop", "-1", "-i", str(effective_bgm),
                        "-filter_complex", filter_complex,
                        "-map", "[vout]", "-map", "[aout]",
                        *enc_args,
                        "-c:a", "aac", "-b:a", "192k", *_STATIC_CONCAT_CFR_ARGS,
                        str(output_path),
                    ]
            else:
                filter_complex = f"{video_filter};{sfx_filter}"
                cmd = [
                    "ffmpeg", "-y",
                    "-f", "concat", "-safe", "0", "-i", str(concat_file),
                    "-i", str(merged_tts),
                    *extra_inputs,
                    "-filter_complex", filter_complex,
                    "-map", "[vout]", "-map", "[aout]",
                    *enc_args,
                    "-c:a", "aac", "-b:a", "192k", *_STATIC_CONCAT_CFR_ARGS,
                    str(output_path),
                ]

        logger.info("[layout] FFmpeg 인코딩 시작: %s", output_path.name)
        # Static timelines use tpad to hold their final frame. Cap every final
        # mux to the audio timeline so segment rounding cannot leave a tail.
        cmd = _cap_output_to_audio(cmd, total_dur)
        ffmpeg_result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if ffmpeg_result.returncode != 0:
            logger.error("[layout] FFmpeg 실패 (returncode=%d):\n%s",
                         ffmpeg_result.returncode, ffmpeg_result.stderr[-3000:])
            raise subprocess.CalledProcessError(
                ffmpeg_result.returncode, cmd, ffmpeg_result.stdout, ffmpeg_result.stderr
            )

        logger.info("[layout] 완료: %s (총 %.1fs)", output_path.name, total_dur)
        return output_path

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def render_layout_video(
    post,
    script,
    output_path: Path | None = None,
    voice_key: str | None = None,
    narration_audio: Path | None = None,
) -> Path:
    """레이아웃 기반 쇼츠 영상 렌더링."""
    from config import settings as s
    from config.settings import load_pipeline_config, VOICE_DEFAULT

    layout = _load_layout()
    _pipeline_cfg = load_pipeline_config()
    voice: str = voice_key or _pipeline_cfg.get("tts_voice", VOICE_DEFAULT)
    rate: str = getattr(s, "TTS_RATE", "+25%")
    sfx_offset: float = getattr(s, "SFX_OFFSET", -0.15)
    max_slots: int = layout["scenes"]["text_only"]["elements"]["text_area"].get("max_slots", 3)
    font_dir: Path = ASSETS_DIR / "fonts"
    audio_dir: Path = getattr(s, "AUDIO_DIR", ASSETS_DIR / "audio")

    video_dir = MEDIA_DIR / "video" / post.site_code
    video_dir.mkdir(parents=True, exist_ok=True)
    if output_path is None:
        output_path = video_dir / f"post_{post.origin_id}_SD.mp4"

    sentences: list[dict] = []
    sentences.append({"text": script.hook, "section": "hook"})
    for body_item in script.body:
        if isinstance(body_item, dict):
            pre_split_lines: list[str] | None = body_item.get("lines")
            body_text = " ".join(pre_split_lines) if pre_split_lines else ""
            block_type = body_item.get("type", "body")
            author = body_item.get("author")
        else:
            body_text = str(body_item)
            pre_split_lines = None
            block_type = "body"
            author = None

        is_quote = block_type == "comment" or any(
            q in body_text for q in ('"', "'", "\u2018", "\u2019", "\u201c", "\u201d")
        )
        sent: dict = {
            "text": body_text,
            "section": "comment" if is_quote else "body",
            "block_type": block_type,
        }
        if author:
            sent["author"] = author
        if pre_split_lines:
            sent["lines"] = pre_split_lines
        sentences.append(sent)
    sentences.append({"text": script.closer, "section": "closer"})

    images: list[str] = post.images if isinstance(post.images, list) else []
    logger.info("[layout] post_id=%d 문장=%d 이미지=%d", post.id, len(sentences), len(images))

    plan = _plan_sequence(sentences, images, layout)
    logger.info("[layout] 씬 계획: %s", [p["type"] for p in plan])

    return _render_pipeline(
        post.id, post.title or "", sentences, plan, images,
        output_path, layout, voice, rate, sfx_offset, max_slots, font_dir, audio_dir,
        narration_audio=Path(narration_audio) if narration_audio else None,
    )


def render_layout_video_from_scenes(
    post,
    scenes: list,
    output_path: Path | None = None,
    save_tts_cache: Path | None = None,
    tts_audio_cache: Path | None = None,
    voice_key: str | None = None,
    narration_audio: Path | None = None,
) -> Path:
    """SceneDirector 출력(SceneDecision 목록)으로 직접 렌더링."""
    from config import settings as s
    from config.settings import load_pipeline_config, VOICE_DEFAULT

    layout = _load_layout()
    _pipeline_cfg = load_pipeline_config()
    voice: str = voice_key or _pipeline_cfg.get("tts_voice", VOICE_DEFAULT)
    rate: str = getattr(s, "TTS_RATE", "+25%")
    sfx_offset: float = getattr(s, "SFX_OFFSET", -0.15)
    max_slots: int = layout["scenes"]["text_only"]["elements"]["text_area"].get("max_slots", 3)
    font_dir: Path = ASSETS_DIR / "fonts"
    audio_dir: Path = getattr(s, "AUDIO_DIR", ASSETS_DIR / "audio")

    video_dir = MEDIA_DIR / "video" / post.site_code
    video_dir.mkdir(parents=True, exist_ok=True)
    if output_path is None:
        output_path = video_dir / f"post_{post.origin_id}_SD.mp4"

    _is_again_spring = getattr(post, "site_code", None) == "again_spring"
    sentences, plan, images = _scenes_to_plan_and_sentences(
        scenes,
        max_comment_items=_AGAIN_SPRING_MAX_COMMENTS if _is_again_spring else None,
    )
    logger.info(
        "[layout:scenes] post_id=%d 씬=%d 문장=%d 이미지=%d",
        post.id, len(scenes), len(sentences), len(images),
    )

    bgm_path: Path | None = None
    for scene in scenes:
        if scene.type == "intro" and getattr(scene, "bgm_path", None):
            candidate = Path(scene.bgm_path)
            if candidate.exists():
                bgm_path = candidate
                logger.info("[layout:scenes] intro bgm_path 적용: %s", bgm_path.name)
            else:
                logger.warning(
                    "[layout:scenes] intro bgm_path 파일 없음: %s — 기존 BGM 방식 fallback",
                    scene.bgm_path,
                )
            break

    # ── 메타 정보 빌드 (제목블록/브레드크럼 메타줄 표시용) ──────────────────
    _stats: dict = post.stats if isinstance(post.stats, dict) else {}
    _author_raw: str = getattr(post, "author", None) or ""
    # SceneDirector가 모든 씬에 동일하게 세팅한 category/view_count(variant_config 유래) —
    # again_spring 전용 필드. 없으면 None → meta.get(...) 쪽에서 자연히 생략됨.
    _scene_category = next(
        (getattr(sc, "category", None) for sc in scenes if getattr(sc, "category", None)), None,
    )
    _scene_view_count = next(
        (getattr(sc, "view_count", None) for sc in scenes if getattr(sc, "view_count", None) is not None),
        None,
    )
    meta: dict = {
        "author": _author_raw or None,          # None이면 config author_fallback 사용
        "time": _relative_time(getattr(post, "created_at", None)),
        "views": _fmt_count(_scene_view_count) if _scene_view_count is not None else _fmt_count(_stats.get("views")),
        "comments": _stats.get("comments_count") or 0,
        "category": _scene_category,
    }

    # Again Spring 외부 잡: 웹 사연 상세(Tone L) 크롬으로 재도색.
    # 브랜드명·author_fallback은 layout.json themes.tone_l(=deep_merge 결과)이 SSOT —
    # 여기서 다시 덮어쓰지 않는다(과거 "다시봄" 하드코딩 오버라이드 제거, 새 디자인의
    # "다시봄 광장" 채널명 / "익명" author_fallback이 그대로 적용되도록).
    # 다른 사이트(와글 기본 옐로우 브랜드)는 이 블록을 타지 않으므로 영향 없음.
    if _is_again_spring:
        import copy
        layout = copy.deepcopy(layout)
        tone_l = layout.get("themes", {}).get("tone_l", {})
        _deep_merge(layout.setdefault("global", {}), tone_l.get("global", {}))
        _deep_merge(layout.setdefault("scenes", {}), tone_l.get("scenes", {}))
        layout["global"]["theme"] = "tone_l"

    return _render_pipeline(
        post.id, post.title or "", sentences, plan, images,
        output_path, layout, voice, rate, sfx_offset, max_slots, font_dir, audio_dir,
        save_tts_cache=save_tts_cache,
        tts_audio_cache=tts_audio_cache,
        bgm_path=bgm_path,
        scenes_list=scenes,
        meta=meta,
        narration_audio=Path(narration_audio) if narration_audio else None,
        comments_fade_enabled=_is_again_spring,
    )
