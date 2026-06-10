"""LTX-2용 영어 비디오 프롬프트 생성 엔진.

LTX-2 Official Prompting Guide 기반:
- 단일 흐르는 단락 (single flowing paragraph)
- 현재 시제 (present tense)
- 3~6문장, 200단어 이내
- 6요소: Shot, Scene, Action, Character, Camera, Audio
- 한국 중심: 한국 인물, 한국 배경, 사운드 묘사 포함
"""

import json
import logging
from pathlib import Path

from ai_worker.script.client import call_ollama_raw
from ai_worker.script.logger import LLMCallTimer, log_llm_call

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# System Prompts — LTX-2 Korea-centric V2
# ──────────────────────────────────────────────

_T2V_PROMPT_SYSTEM_V2 = """\
You are a cinematographer writing a prompt for LTX-2 AI video generation.
Write ONE flowing paragraph in English describing a 4-second photorealistic video clip.
Compose the paragraph in this exact order, covering the 6 LTX-2 elements:
1. SHOT — framing and lens (e.g. medium shot, eye-level, natural 35mm look).
2. SCENE — the Korean location and time of day.
3. ACTION — what unfolds chronologically across the 4 seconds, with concrete gestures and movement.
4. CHARACTER — the Korean person: look, clothing, and facial expression.
5. CAMERA — keep it almost still (see CAMERA RULE).
6. AUDIO — ambient sound, speech tone, and background noise for sound generation.

SETTING: Modern South Korea — Korean people, streets, offices, cafes, apartments, convenience stores.

REALISM (kill the "AI video" look):
- Shot on a real camera; candid, documentary-style framing like genuine footage.
- Natural skin texture with visible pores and small imperfections — never plastic, waxy, or airbrushed.
- Motivated natural light (window light, overcast sky, street lamps); no studio gloss.
- Grounded, true-to-life color. NO oversaturation, NO CGI sheen, NO over-glossy highlights.

MOOD STYLING (tonal reference only — realism always wins; treat each cue as a subtle, photorealistic equivalent, never literal oversaturation or stylized grading):
- Visual tone: {style_detail}
- Lean the color toward: {color_palette}
- Overall atmosphere: {atmosphere}

CAMERA RULE (critical for LTX-2):
- Mood camera options for tone: {camera_options}
- BUT choose only the SINGLE gentlest move and apply it subtly, or hold the frame fully static.
- Never combine moves; motion stays minimal, slow, and motivated.

HARD CONSTRAINTS:
- Present tense, chronological, ONE paragraph, under 150 words — always finish the AUDIO description.
- Korean people and Korean settings only.
- ALWAYS include SOUND descriptions.
- NEVER include: cyberpunk, sci-fi, fantasy, anime, abstract art, neon, western or European settings.

PERSON FALLBACK TIERS:
- Prefer medium shots (waist-up or full body) over extreme face close-ups.
- For emotional dialogue, use side profiles or over-shoulder angles.
- If a person is hard to render, fall back to object/environment focus (empty room, laptop screen, coffee cup).
- Last resort: a cute golden retriever puppy or kitten, filmed photorealistically in the same realistic style.

Mood: {mood}

Korean source text: {korean_text}"""

_I2V_SYSTEM = """\
You write motion prompts for LTX-2 Image-to-Video mode.
An input image already shows the scene, characters, and composition.
Describe ONLY the motion, camera movement, and sound that animate the existing image.

RULES:
- ONE paragraph, 2-4 sentences, present tense.
- Do NOT re-describe the scene or characters — they already exist in the image.
- Focus on subtle micro-motions: slow breathing, hair drifting, a single blink, fabric rustling, steam rising.
- PRESERVE identity and shape: faces and bodies stay stable — no face morphing, no warping, no melting, no shape-shifting, no extra or vanishing limbs.
- PRESERVE appearance: keep clothing, colors, background, and lighting consistent with the input image — animate only motion, never restyle.
- Pick ONE gentle camera move or hold static (subtle dolly in, slow pan, gentle tilt). Never combine moves.
- Match motion energy to the mood — calm and slow for tender or sad moods, a touch livelier for upbeat moods — but always keep it subtle.
- Include SOUND descriptions: ambient sound, speech tone, background noise.

EXAMPLE (touching mood):
"She breathes slowly and her eyes soften into a faint smile, a few strands of hair drifting in a gentle draft while her face stays perfectly stable. The camera holds a quiet medium shot, then eases into a barely perceptible dolly in. Warm room tone, a soft sigh, and a faint acoustic melody play underneath."

---
Mood: {mood}
Korean context: {korean_text}

Write the motion prompt:"""

# ──────────────────────────────────────────────
# Negative Prompt V2
# ──────────────────────────────────────────────

NEGATIVE_PROMPT = (
    "worst quality, inconsistent motion, blurry, jittery, distorted, "
    "watermarks, anime, cartoon, 3d render, CGI, "
    "cyberpunk, sci-fi, futuristic, neon lights, abstract, "
    "deformed hands, extra fingers, bad anatomy, "
    "ugly, duplicate, morbid, mutilated, "
    "western faces, caucasian, european setting, "
    "oversaturated, plastic skin, airbrushed, waxy skin, over-glossy, "
    "face morphing, warping, identity drift"
)

# ──────────────────────────────────────────────
# Video Styles (mood → style hint)
# ──────────────────────────────────────────────

_VIDEO_STYLES: dict | None = None


def _load_video_styles() -> dict:
    """config/video_styles.json 로드 (캐시)."""
    global _VIDEO_STYLES
    if _VIDEO_STYLES is None:
        path = Path(__file__).resolve().parent.parent.parent / "config" / "video_styles.json"
        try:
            with open(path, encoding="utf-8") as f:
                _VIDEO_STYLES = json.load(f)
        except Exception as e:
            logger.error("[prompt] video_styles.json 로딩 실패: %s", e)
            _VIDEO_STYLES = {}
    return _VIDEO_STYLES


def _get_style_block(mood: str) -> dict:
    """mood → 비주얼 스타일 상세 블록.

    video_styles.json의 리스트 필드(camera_hints/color_palette)는 콤마로 join한다.
    미존재 mood는 daily 폴백. 반환 키: style_hint/camera_hints/color_palette/atmosphere.
    """
    styles = _load_video_styles()
    style_data = styles.get(mood) or styles.get("daily", {})
    camera_hints = style_data.get("camera_hints", [])
    color_palette = style_data.get("color_palette", [])
    return {
        "style_hint": style_data.get("style_hint", "photorealistic, natural lighting"),
        "camera_hints": ", ".join(camera_hints) if isinstance(camera_hints, list) else str(camera_hints),
        "color_palette": ", ".join(color_palette) if isinstance(color_palette, list) else str(color_palette),
        "atmosphere": style_data.get("atmosphere", "cinematic, natural lighting"),
    }


def _get_style_hint(mood: str) -> str:
    """mood에서 간결한 스타일 힌트 추출 (atmosphere 필드 사용, _get_style_block 위임)."""
    return _get_style_block(mood)["atmosphere"]


# ──────────────────────────────────────────────
# Prompt Engine
# ──────────────────────────────────────────────

class VideoPromptEngine:
    """LTX-2 프롬프트 생성기 (공식 가이드 + 한국 중심)."""

    def generate_prompt(
        self,
        text_lines: list[str],
        mood: str,
        title: str = "",
        body_summary: str = "",
        has_init_image: bool = False,
        post_id: int | None = None,
        scene_index: int | None = None,
    ) -> str:
        """한국어 텍스트 → LTX-2용 영어 프롬프트 변환.

        body_summary는 시그니처 호환을 위해 받지만 현재 프롬프트에 주입하지 않는다
        (씬-로컬 컨텍스트 = text_lines + title만 사용).
        """
        korean_text = " ".join(text_lines)
        if title:
            korean_text = f"[제목: {title}] {korean_text}"

        video_mode = "i2v" if has_init_image else "t2v"
        call_type = f"video_prompt_{video_mode}"

        if has_init_image:
            prompt_input = _I2V_SYSTEM.format(
                korean_text=korean_text,
                mood=mood,
            )
            max_tok, temp = 120, 0.3
        else:
            style = _get_style_block(mood)
            style_hint = style["style_hint"]  # _scene_meta 로깅 호환용
            prompt_input = _T2V_PROMPT_SYSTEM_V2.format(
                mood=mood,
                style_detail=style["style_hint"],
                color_palette=style["color_palette"],
                camera_options=style["camera_hints"],
                atmosphere=style["atmosphere"],
                korean_text=korean_text,
            )
            max_tok, temp = 220, 0.4

        success = True
        error_msg: str | None = None
        raw = ""
        with LLMCallTimer() as timer:
            try:
                raw = call_ollama_raw(prompt=prompt_input, max_tokens=max_tok, temperature=temp)
            except Exception as exc:
                success = False
                error_msg = str(exc)
                raise
            finally:
                _scene_meta = {
                    "scene_index": scene_index,
                    "video_mode": video_mode,
                    "korean_text": korean_text,
                    "mood": mood,
                    "style_hint": style_hint if not has_init_image else None,
                    "korean_translation": None,
                }
                log_llm_call(
                    call_type=call_type,
                    post_id=post_id,
                    model_name="",
                    prompt_text=prompt_input,
                    raw_response=raw,
                    parsed_result=_scene_meta,
                    content_length=len(korean_text),
                    success=success,
                    error_message=error_msg,
                    duration_ms=timer.elapsed_ms,
                )

        return _clean_prompt(raw)

    def simplify_prompt(
        self,
        original_prompt: str,
        post_id: int | None = None,
        scene_index: int | None = None,
    ) -> str:
        """재시도용 프롬프트 단순화 (2-3문장).

        카메라 + 주요 동작만 남기고 오디오, 세부 조명, 보조 캐릭터 제거.
        """
        system = (
            "Simplify this video prompt to 2-3 short sentences. "
            "Keep ONLY: the main subject, one key action, and the camera angle. "
            "Remove audio, detailed lighting, and secondary characters. "
            "Keep it photorealistic with a Korean subject and setting. "
            "Present tense, one paragraph.\n\n"
            f"Original: {original_prompt}\n\nSimplified:"
        )
        success = True
        error_msg: str | None = None
        raw = ""
        with LLMCallTimer() as timer:
            try:
                raw = call_ollama_raw(prompt=system, max_tokens=80, temperature=0.2)
            except Exception as exc:
                success = False
                error_msg = str(exc)
                raise
            finally:
                _scene_meta = {"scene_index": scene_index, "video_mode": "simplify"}
                log_llm_call(
                    call_type="video_prompt_simplify",
                    post_id=post_id,
                    model_name="",
                    prompt_text=system,
                    raw_response=raw,
                    parsed_result=_scene_meta,
                    content_length=len(original_prompt),
                    success=success,
                    error_message=error_msg,
                    duration_ms=timer.elapsed_ms,
                )
        return _clean_prompt(raw)

    def generate_batch(
        self,
        scenes: list,
        mood: str,
        title: str = "",
        body_summary: str = "",
        post_id: int | None = None,
    ) -> list:
        """여러 씬의 비디오 프롬프트를 일괄 생성.

        Phase 7에서 LLM 호출이 제로(0)가 되도록,
        원본 프롬프트와 함께 simplified 버전도 미리 생성한다.
        """
        for i, scene in enumerate(scenes):
            if getattr(scene, "video_mode", None) not in ("t2v", "i2v"):
                continue
            try:
                text_lines = [
                    line.get("text", "") if isinstance(line, dict) else str(line)
                    for line in scene.text_lines
                ]
                scene.video_prompt = self.generate_prompt(
                    text_lines=text_lines,
                    mood=mood,
                    title=title,
                    body_summary=body_summary,
                    has_init_image=(scene.video_mode == "i2v"),
                    post_id=post_id,
                    scene_index=i,
                )
            except Exception as e:
                logger.error("[prompt] 씬 %d 프롬프트 생성 실패: %s", i, e)
                scene.video_prompt = None
                scene.video_prompt_simplified = None
                continue

            # Phase 7 재시도용 simplified 프롬프트 미리 생성 (LLM 호출 제로 보장)
            # generate_prompt 성공 후 별도 예외 처리 — 실패 시 원본으로 폴백
            try:
                scene.video_prompt_simplified = self.simplify_prompt(
                    scene.video_prompt,
                    post_id=post_id,
                    scene_index=i,
                )
            except Exception as e:
                logger.warning("[prompt] 씬 %d simplified 생성 실패 — 원본으로 폴백: %s", i, e)
                scene.video_prompt_simplified = scene.video_prompt

            logger.info(
                "[prompt] 씬 %d 프롬프트 생성 완료 (%d자, simplified %d자)",
                i, len(scene.video_prompt),
                len(scene.video_prompt_simplified),
            )
        return scenes


def _clean_prompt(raw: str) -> str:
    """LLM 출력을 단일 단락으로 정리."""
    prompt = " ".join(raw.strip().splitlines()).strip()
    # 따옴표 래핑 제거
    if prompt.startswith('"') and prompt.endswith('"'):
        prompt = prompt[1:-1].strip()
    # 마크다운 헤더 제거
    if prompt.startswith("#"):
        lines = prompt.split(". ", 1)
        prompt = lines[1] if len(lines) > 1 else prompt
    return prompt
