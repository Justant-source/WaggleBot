"""LTX-2용 영어 비디오 프롬프트 생성 엔진 (V3).

LTX-2 Official Prompting Guide 기반:
- 단일 흐르는 단락 (single flowing paragraph), 현재 시제, 6요소(Shot/Scene/Action/Character/Camera/Audio)
- 한국 중심: 한국 인물, 한국 배경, 사운드 묘사 포함

V3 개편 (지속시청시간 목표):
- 동적 클립 길이(4~6초, estimated_tts_sec 기반) — "4초" 하드코딩 제거
- 스토리 컨텍스트(제목+요약) 주입 — 씬 조각만으로 생기던 맥락 단절 해소
- 비주얼 앵커: post당 1회 생성한 주인공/장소 묘사를 전 T2V 씬에 재사용 (클립 간 연속성)
- I2V vision brief: api 백엔드에서 이미지 내용을 분석해 모션이 피사체와 모순되지 않게 함
- 출력 검증 + 1회 재시도 + 결정적 폴백 — 메타 응답("I'm an AI...") 유출 차단
- system/user 분리 + cache_prefix — api 백엔드 프롬프트 캐싱 적중
"""

import json
import logging
import re
from pathlib import Path

from ai_worker.llm.transport import call_llm, llm_backend_supports_vision
from ai_worker.script.logger import LLMCallTimer, log_llm_call

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# System Prompts — LTX-2 Korea-centric V3
# (무치환 정적 텍스트 — api 백엔드 prompt caching 대상)
# ──────────────────────────────────────────────

_T2V_SYSTEM_V3 = """\
You are a cinematographer writing one prompt for the LTX-2 AI video model.
Write ONE flowing paragraph in English describing a photorealistic video clip
of the exact duration given in the task. Cover the 6 LTX-2 elements in order:
1. SHOT — framing and lens (e.g. medium shot, eye-level, natural 35mm look).
2. SCENE — the Korean location and time of day.
3. ACTION — one clear action with a beginning, development, and end state
   across the clip duration (see MOTION ARC).
4. CHARACTER — the Korean person: look, clothing, facial expression.
5. CAMERA — one gentle move or static (see CAMERA RULE).
6. AUDIO — ambient sound, vocal tone, background noise.

MOTION ARC (critical for viewer retention):
- The clip must visibly evolve: opening state → one continuous action → end state.
- Never a frozen tableau; something is always in motion (a gesture, an object,
  light, passers-by).
- End on a subtle unresolved beat (a glance up, a turn toward something
  off-frame) so the video feels like it continues.

VISUAL CONTINUITY:
- The task may include a VISUAL ANCHOR describing the recurring protagonist and
  location of this story. Reuse that exact look, clothing, and place unless
  THIS SCENE clearly happens elsewhere.

SETTING: Modern South Korea — Korean people, streets, offices, cafes,
apartments, convenience stores.

REALISM (kill the "AI video" look):
- Shot on a real camera; candid, documentary-style framing like genuine footage.
- Natural skin texture with visible pores and small imperfections — never
  plastic, waxy, or airbrushed.
- Motivated natural light (window light, overcast sky, street lamps); no studio gloss.
- Grounded, true-to-life color. NO oversaturation, NO CGI sheen.

CAMERA RULE (critical for LTX-2):
- Choose only the SINGLE gentlest move from the mood's camera options and apply
  it subtly, or hold the frame fully static. Never combine moves.
- If the task names the previous clip's framing, choose a DIFFERENT framing.

PERSON FALLBACK:
- Prefer waist-up or full-body framing over extreme face close-ups.
- For emotional lines use side profiles or two-shot (both subjects in frame);
  avoid over-shoulder shots where a face fills the extreme foreground —
  distilled 8-step renders that as cartoon-like.
- If a person is hard to render, focus on objects/environment instead
  (phone screen, coffee cup, doorway, empty room).

OUTPUT RULES (absolute):
- Output ONLY the prompt paragraph. No preamble, no questions, no notes,
  no markdown, no Korean.
- The Korean lines you receive may be a mid-sentence fragment or cliffhanger —
  that is intentional script pacing. NEVER ask for more text; infer the moment
  and write the prompt.
- Present tense, chronological, under 160 words, always finish the AUDIO part.
- NEVER include: cyberpunk, sci-fi, fantasy, anime, abstract art, neon,
  western or European settings."""

_I2V_SYSTEM_V3 = """\
You write motion prompts for the LTX-2 Image-to-Video model.
The input image is the first frame of the clip; it already defines the scene,
subjects, and composition. Describe ONLY the motion, camera movement, and sound
that animate it for the duration given in the task.

RULES:
- ONE paragraph, 2-4 sentences, present tense.
- Do NOT re-describe or restyle the scene — animate what already exists.
- Motion must fit the actual subject shown: people → slow breathing, a blink,
  small head or hand movement; food/objects → rising steam, shifting light,
  gentle parallax; outdoor scenes → drifting clouds, passing cars, swaying
  branches; screenshots/documents → slow push-in only.
- The motion evolves slightly from start to end — no frozen freeze-frame,
  no looping feel — while staying subtle.
- PRESERVE identity and shape: faces and bodies stay stable — no face morphing,
  no warping, no melting, no extra or vanishing limbs.
- PRESERVE appearance: keep clothing, colors, background, and lighting
  consistent with the input image — animate motion only, never restyle.
- Pick ONE gentle camera move or hold static (subtle dolly in, slow pan,
  gentle tilt). Never combine moves.
- If you are NOT told what the image shows and cannot infer it confidently
  from the Korean context, animate ONLY the camera (slow push-in or gentle
  parallax) plus ambient sound — that is safe for any image.
- Always include SOUND: ambient room/street tone, breaths or murmurs,
  background noise.

OUTPUT RULES (absolute): output ONLY the motion prompt paragraph — no preamble,
no questions, no Korean. The Korean context may be a mid-sentence fragment;
never ask for more text."""

_ANCHOR_PROMPT = """\
Read this Korean community post and define the recurring visual identity for a
short video series narrating it. Output 2-3 English sentences, present tense:
1) The protagonist: a Korean person — gender, age range, clothing, one
   distinctive feature.
2) The primary location and time of day, with its natural light.
3) Optionally one secondary person if the story clearly involves one.
No plot, no emotions, no camera notes — only reusable appearance and place
facts. Output ONLY the sentences, no preamble, no Korean.

Title: {title}
Story: {body_summary}
Mood: {mood}"""

_IMAGE_BRIEF_PROMPT = """\
Describe this image in 1-2 factual English sentences for a video animator:
the main subject and their pose or state, the setting, and the lighting.
No interpretation, no story, no Korean. Output only the description."""

# ──────────────────────────────────────────────
# Negative Prompt (full 모드용 — distilled CFG 1.0에서는 무효)
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
# 출력 검증 + 결정적 폴백
# ──────────────────────────────────────────────

# LLM 메타 응답 검출 마커 (소문자 비교) — 실측 유출 사례 기반 최소 집합
_META_MARKERS: tuple[str, ...] = (
    "i'm ", "i am an", "as an ai", "i cannot", "i can't", "i need to",
    "could you", "please provide", "i appreciate", "an ai assistant",
    "kiro", "claude", "my role", "clarify",
)

_RETRY_SUFFIX = (
    "\n\nIMPORTANT: Your previous output was rejected. Output ONLY the English "
    "prompt paragraph itself — no questions, no preamble, no self-reference, "
    "no Korean."
)

# 실패 사유별 재시도 보강 지시 (E2E 관찰: 사유를 명시해야 재시도 성공률이 오름)
_RETRY_HINTS: dict[str, str] = {
    "korean_text": (
        " Your output contained Korean characters — never quote the Korean "
        "lines; describe everything in English only."
    ),
    "question_mark": (
        " Your output contained a question mark — use declarative sentences only."
    ),
    "too_long": " Keep it under 150 words.",
    "too_short": " Write a full paragraph of at least 60 words.",
}

# LLM 2회 실패 시 사용하는 mood별 결정적 T2V 폴백 (쓰레기 프롬프트 유입 차단)
_FALLBACK_PROMPTS: dict[str, str] = {
    "humor": (
        "A bright Korean office break room at midday, sunlight bouncing off a white "
        "table where a steaming paper coffee cup sits beside a half-eaten snack; a "
        "hand reaches in, hesitates, then quietly drags the snack out of frame as the "
        "steam keeps curling upward. The camera holds an eye-level static shot with a "
        "hint of handheld sway. Office hum, distant keyboard clicks, and a muffled "
        "burst of coworkers' laughter in the background."
    ),
    "touching": (
        "Late golden-hour light pours through a Korean apartment window, a thin "
        "curtain drifting as dust motes float through the warm beam over a worn "
        "family photo on the sill; the light slowly creeps across the frame, catching "
        "the glass. The camera eases into a barely perceptible dolly in toward the "
        "window. Soft room tone, a distant piano melody, and the faint rustle of fabric."
    ),
    "anger": (
        "Under harsh fluorescent light in a Korean office at night, a fist rests "
        "beside a phone on a cluttered desk, knuckles slowly tightening as a "
        "notification glows on the screen; papers shift slightly as the hand presses "
        "down. The camera stays in a locked-off static close shot. A low "
        "air-conditioner hum, the buzz of the lamp, and a muffled argument bleeding "
        "through the wall."
    ),
    "sadness": (
        "Rain streaks down a Korean apartment window at dusk, blurred city lights "
        "trembling beyond the glass as droplets gather and slide in slow trails; the "
        "room inside stays dim and still, a cooling cup of tea faintly steaming on "
        "the sill. The camera holds a static wide shot, then tilts down almost "
        "imperceptibly. Steady rain patter, distant traffic hiss, and a quiet room "
        "tone underneath."
    ),
    "horror": (
        "A dark Korean apartment hallway at night, lit only by a single flickering "
        "wall lamp that throws long shadows across the closed doors; at the far end, "
        "the darkness seems to shift as the flicker stutters and steadies again. The "
        "camera creeps forward in a slow, almost imperceptible push-in. Oppressive "
        "silence, a low refrigerator hum, and one faint creak of the wooden floor."
    ),
    "info": (
        "A tidy Korean office desk in clean daylight, a laptop open beside a notebook "
        "and a cup of coffee whose steam rises in a thin steady line; the cursor "
        "blinks on the screen as a pen rolls slightly when a hand sets it down and "
        "slides out of frame. The camera pans smoothly and slowly across the desk. "
        "Quiet keyboard clicks, a soft chair creak, and calm office ambience."
    ),
    "controversy": (
        "A dim Korean study at night where printed documents lie scattered under a "
        "desk lamp, a phone screen glowing face-up between them as a highlighted line "
        "catches the light; the lamp's glow flickers faintly while a page edge lifts "
        "in the draft. The camera pushes in slowly toward the documents. Paper "
        "rustle, a low news broadcast murmuring from another room, and a quiet "
        "electrical hum."
    ),
    "daily": (
        "A lived-in Korean cafe table by the window in soft afternoon daylight, steam "
        "curling from a fresh latte as blurred passers-by drift along the street "
        "outside; a notebook page lifts gently when the door opens somewhere "
        "off-frame. The camera holds a casual eye-level shot with gentle handheld "
        "sway. Low cafe chatter, cups clinking, and a soft door chime."
    ),
    "shock": (
        "A Korean convenience store counter under stark white light, a phone lying "
        "face-up on the floor where it was just dropped, screen still lit and casting "
        "a glow upward; the screen flickers once as the overhead light buzzes and a "
        "shadow stops mid-step at the edge of the frame. The camera holds static on "
        "the phone, then pushes in subtly. A sharp clatter echo fading into freezer "
        "hum and tense silence."
    ),
}

_FALLBACK_I2V = (
    "The scene holds nearly still as the camera eases into a slow, barely "
    "perceptible push-in with gentle parallax; light shifts softly across the frame "
    "while everything keeps its exact shape and color. Quiet ambient room tone with "
    "faint distant street noise underneath."
)

# 샷 다양성 추적용 — T2V 프롬프트에서 추출할 프레이밍 키워드 (긴 것 우선 매칭)
_SHOT_TYPES: tuple[str, ...] = (
    "extreme close-up", "close-up", "medium shot", "wide shot", "full body",
    "over-the-shoulder", "over-shoulder", "side profile", "two-shot",
)


def _validate_prompt(prompt: str) -> tuple[bool, str]:
    """LLM 출력이 유효한 비디오 프롬프트인지 검증한다.

    Returns:
        (ok, reason) — ok=False면 reason에 실패 사유.
    """
    if not prompt or len(prompt) < 40:
        return False, "too_short"
    # LTX-2는 상세 프롬프트에 강함 — 장황하지만 정상인 출력을 폴백으로 버리지 않도록
    # 상한은 명백한 폭주(반복·잡설)만 거르는 수준으로 느슨하게 둔다
    if len(prompt) > 1600:
        return False, "too_long"
    if re.search(r"[가-힣]", prompt):
        return False, "korean_text"
    if "?" in prompt:
        return False, "question_mark"
    lowered = prompt.lower()
    for marker in _META_MARKERS:
        if marker in lowered:
            return False, f"meta_marker:{marker.strip()}"
    return True, "ok"


def _clamp_duration(sec: float) -> float:
    """씬 TTS 예상 시간을 클립 길이 정책(4~6초)으로 클램프한다."""
    if sec <= 0:
        return 4.0
    return min(max(sec, 4.0), 6.0)


def _extract_shot_type(prompt: str) -> str | None:
    """T2V 프롬프트에서 프레이밍 키워드를 추출한다 (다음 씬 샷 다양성용)."""
    lowered = prompt.lower()
    for shot in _SHOT_TYPES:
        if shot in lowered:
            return shot
    return None


def _fallback_prompt(mood: str, video_mode: str) -> str:
    """LLM 무관 결정적 폴백 프롬프트."""
    if video_mode == "i2v":
        return _FALLBACK_I2V
    return _FALLBACK_PROMPTS.get(mood) or _FALLBACK_PROMPTS["daily"]


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
# 동적 user prompt 빌더
# ──────────────────────────────────────────────

def _build_t2v_user_prompt(
    korean_text: str,
    mood: str,
    duration_sec: float,
    title: str,
    story_context: str,
    visual_anchor: str,
    prev_shot_type: str | None,
) -> str:
    """T2V 동적 입력부 구성 (정적 system과 분리 — 캐싱 적중용)."""
    style = _get_style_block(mood)
    parts: list[str] = [
        f"Clip duration: about {duration_sec:g} seconds.",
        f"Mood: {mood}",
        "MOOD STYLING (subtle photorealistic equivalents only):",
        f"- Visual tone: {style['style_hint']}",
        f"- Lean the color toward: {style['color_palette']}",
        f"- Camera options: {style['camera_hints']}",
        f"- Overall atmosphere: {style['atmosphere']}",
    ]
    if title or story_context:
        parts.append("")
        parts.append(
            "STORY CONTEXT (Korean web post being narrated — for understanding "
            "only, do not depict all of it):"
        )
        if title:
            parts.append(f"- Title: {title}")
        if story_context:
            parts.append(f"- Story: {story_context}")
    if visual_anchor:
        parts.append("")
        parts.append(f"VISUAL ANCHOR (reuse across all clips):\n{visual_anchor}")
    if prev_shot_type:
        parts.append("")
        parts.append(f"Previous clip framing: {prev_shot_type} — use a different framing.")
    parts.append("")
    parts.append("THIS SCENE — the narration lines this clip illustrates. Depict THIS moment:")
    parts.append(korean_text)
    parts.append("")
    parts.append("Write the prompt paragraph now.")
    return "\n".join(parts)


def _build_i2v_user_prompt(
    korean_text: str,
    mood: str,
    duration_sec: float,
    title: str,
    image_brief: str | None,
    image_category: str | None,
) -> str:
    """I2V 동적 입력부 구성."""
    parts: list[str] = [
        f"Clip duration: about {duration_sec:g} seconds.",
        f"Mood: {mood} — match the motion energy (calm and slow for tender or "
        "sad moods, slightly livelier for upbeat ones) but always subtle.",
    ]
    if image_brief:
        parts.append(f"WHAT THE IMAGE SHOWS (trust this over guesses):\n{image_brief}")
    elif image_category:
        parts.append(
            f"The image is not analyzed. Category hint: {image_category}. Infer "
            "the likely subject from the Korean context; if uncertain, animate "
            "only the camera."
        )
    else:
        parts.append(
            "The image is not analyzed. Infer the likely subject from the Korean "
            "context; if uncertain, animate only the camera."
        )
    if title:
        parts.append(f"Story title: {title}")
    parts.append(f"Korean context: {korean_text}")
    parts.append("")
    parts.append("Write the motion prompt now.")
    return "\n".join(parts)


# ──────────────────────────────────────────────
# Prompt Engine
# ──────────────────────────────────────────────

class VideoPromptEngine:
    """LTX-2 프롬프트 생성기 V3 (공식 가이드 + 한국 중심 + 연속성/검증)."""

    def _invoke_llm(
        self,
        *,
        call_type: str,
        prompt: str,
        system: str | None,
        max_tokens: int,
        temperature: float,
        post_id: int | None,
        scene_meta: dict,
        timeout: int = 90,
        images: list[Path] | None = None,
    ) -> tuple[str, str | None]:
        """call_llm 호출 + LLMLog 기록. (raw, error_message) 반환 — 예외 미전파."""
        success = True
        error_msg: str | None = None
        raw = ""
        with LLMCallTimer() as timer:
            try:
                raw = call_llm(
                    prompt,
                    system=system,
                    cache_prefix=bool(system),
                    call_type=call_type,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    timeout=timeout,
                    post_id=post_id,
                    images=images,
                )
            except Exception as exc:
                success = False
                error_msg = str(exc)
            finally:
                full_prompt = f"{system}\n\n{prompt}" if system else prompt
                log_llm_call(
                    call_type=call_type,
                    post_id=post_id,
                    model_name="",
                    prompt_text=full_prompt,
                    raw_response=raw,
                    parsed_result=scene_meta,
                    content_length=len(prompt),
                    success=success,
                    error_message=error_msg,
                    duration_ms=timer.elapsed_ms,
                )
        return raw, error_msg

    def generate_prompt(
        self,
        text_lines: list[str],
        mood: str,
        title: str = "",
        body_summary: str = "",
        has_init_image: bool = False,
        post_id: int | None = None,
        scene_index: int | None = None,
        *,
        duration_sec: float = 4.0,
        visual_anchor: str = "",
        image_brief: str | None = None,
        image_category: str | None = None,
        prev_shot_type: str | None = None,
    ) -> str:
        """한국어 텍스트 → LTX-2용 영어 프롬프트 변환.

        검증 실패 시 1회 재시도(출력 전용 강화), 재실패 시 결정적 폴백을 반환한다.
        LLM 전송 오류도 폴백으로 흡수 — 예외를 던지지 않는다.
        """
        korean_text = " ".join(text_lines)
        video_mode = "i2v" if has_init_image else "t2v"
        call_type = f"video_prompt_{video_mode}"
        dur = _clamp_duration(duration_sec)

        if has_init_image:
            system = _I2V_SYSTEM_V3
            user_prompt = _build_i2v_user_prompt(
                korean_text=korean_text,
                mood=mood,
                duration_sec=dur,
                title=title,
                image_brief=image_brief,
                image_category=image_category,
            )
            max_tok, temp = 160, 0.3
        else:
            system = _T2V_SYSTEM_V3
            user_prompt = _build_t2v_user_prompt(
                korean_text=korean_text,
                mood=mood,
                duration_sec=dur,
                title=title,
                story_context=body_summary,
                visual_anchor=visual_anchor,
                prev_shot_type=prev_shot_type,
            )
            max_tok, temp = 300, 0.4

        scene_meta = {
            "scene_index": scene_index,
            "video_mode": video_mode,
            "korean_text": korean_text,
            "mood": mood,
            "duration_sec": dur,
            "has_visual_anchor": bool(visual_anchor),
            "has_image_brief": bool(image_brief),
        }

        raw, err = self._invoke_llm(
            call_type=call_type,
            prompt=user_prompt,
            system=system,
            max_tokens=max_tok,
            temperature=temp,
            post_id=post_id,
            scene_meta=scene_meta,
        )
        cleaned = _clean_prompt(raw)
        ok, reason = _validate_prompt(cleaned) if err is None else (False, f"llm_error:{err}")
        if ok:
            return cleaned

        # 1회 재시도 — 출력 전용 강화 + 실패 사유별 보강 지시
        logger.warning(
            "[prompt] 씬 %s %s 프롬프트 검증 실패(%s) — 재시도",
            scene_index, video_mode, reason,
        )
        retry_suffix = _RETRY_SUFFIX + _RETRY_HINTS.get(reason.split(":")[0], "")
        raw2, err2 = self._invoke_llm(
            call_type=call_type,
            prompt=user_prompt + retry_suffix,
            system=system,
            max_tokens=max_tok,
            temperature=temp,
            post_id=post_id,
            scene_meta={**scene_meta, "retried": True, "first_fail_reason": reason},
        )
        cleaned2 = _clean_prompt(raw2)
        ok2, reason2 = _validate_prompt(cleaned2) if err2 is None else (False, f"llm_error:{err2}")
        if ok2:
            return cleaned2

        logger.error(
            "[prompt] 씬 %s %s 프롬프트 재시도도 실패(%s) — 결정적 폴백 사용",
            scene_index, video_mode, reason2,
        )
        return _fallback_prompt(mood, video_mode)

    def generate_visual_anchor(
        self,
        title: str,
        body_summary: str,
        mood: str,
        post_id: int | None = None,
    ) -> str:
        """post당 1회: 전 클립이 공유할 주인공/장소 앵커(영어 2~3문장)를 생성한다.

        실패·검증 불통과 시 빈 문자열 반환 — 파이프라인을 중단시키지 않는다.
        """
        if not (title or body_summary):
            return ""
        prompt = _ANCHOR_PROMPT.format(
            title=title or "(none)",
            body_summary=body_summary or "(none)",
            mood=mood,
        )
        raw, err = self._invoke_llm(
            call_type="video_visual_anchor",
            prompt=prompt,
            system=None,
            max_tokens=150,
            temperature=0.3,
            post_id=post_id,
            scene_meta={"video_mode": "anchor", "mood": mood},
            timeout=60,
        )
        if err is not None:
            logger.warning("[prompt] 비주얼 앵커 생성 실패 — 앵커 없이 진행: %s", err)
            return ""
        cleaned = _clean_prompt(raw)
        ok, reason = _validate_prompt(cleaned)
        if not ok:
            logger.warning("[prompt] 비주얼 앵커 검증 실패(%s) — 앵커 없이 진행", reason)
            return ""
        return cleaned

    def generate_image_brief(
        self,
        image_path: Path,
        post_id: int | None = None,
        scene_index: int | None = None,
    ) -> str | None:
        """I2V 초기 이미지의 내용을 vision으로 1~2문장 분석한다 (api 백엔드 전용).

        cli 백엔드/파일 누락/전송 오류/검증 실패 시 None — 호출자는 카테고리 힌트로 폴백.
        """
        if not llm_backend_supports_vision():
            return None
        path = Path(image_path)
        if not path.is_file():
            logger.warning("[prompt] 씬 %s brief 이미지 누락: %s", scene_index, path)
            return None
        raw, err = self._invoke_llm(
            call_type="video_image_brief",
            prompt=_IMAGE_BRIEF_PROMPT,
            system=None,
            max_tokens=120,
            temperature=0.2,
            post_id=post_id,
            scene_meta={"video_mode": "image_brief", "scene_index": scene_index},
            timeout=60,
            images=[path],
        )
        if err is not None:
            logger.warning(
                "[prompt] 씬 %s 이미지 brief 실패(vision 미지원 가능성): %s",
                scene_index, err,
            )
            return None
        cleaned = _clean_prompt(raw)
        ok, reason = _validate_prompt(cleaned)
        if not ok:
            logger.warning("[prompt] 씬 %s 이미지 brief 검증 실패(%s)", scene_index, reason)
            return None
        return cleaned

    def simplify_prompt(
        self,
        original_prompt: str,
        post_id: int | None = None,
        scene_index: int | None = None,
        *,
        visual_anchor: str = "",
    ) -> str:
        """재시도용 프롬프트 단순화 (2-3문장).

        카메라 + 주요 동작만 남기고 오디오, 세부 조명, 보조 캐릭터 제거.
        앵커가 있으면 주인공/장소 묘사는 유지시킨다. 실패 시 원본 반환.
        """
        anchor_line = (
            " Keep the same protagonist appearance and location as the original."
            if visual_anchor else ""
        )
        system = (
            "Simplify this video prompt to 2-3 short sentences. "
            "Keep ONLY: the main subject, one key action that still evolves from "
            "start to end, and the camera angle. "
            "Remove audio, detailed lighting, and secondary characters. "
            "Keep it photorealistic with a Korean subject and setting."
            + anchor_line +
            " Present tense, one paragraph. Output only the simplified prompt.\n\n"
            f"Original: {original_prompt}\n\nSimplified:"
        )
        raw, err = self._invoke_llm(
            call_type="video_prompt_simplify",
            prompt=system,
            system=None,
            max_tokens=100,
            temperature=0.2,
            post_id=post_id,
            scene_meta={"scene_index": scene_index, "video_mode": "simplify"},
        )
        if err is not None:
            return original_prompt
        cleaned = _clean_prompt(raw)
        ok, _reason = _validate_prompt(cleaned)
        return cleaned if ok else original_prompt

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

        V3: 앵커 1회 생성(연속성) → 씬별 동적 길이/brief/샷 다양성 주입.
        호출 시그니처는 불변 — core/processor·pipeline/content_processor 양쪽 공용.
        """
        video_scenes = [s for s in scenes if getattr(s, "video_mode", None) in ("t2v", "i2v")]
        if not video_scenes:
            return scenes

        # post당 1회: 비주얼 앵커 (T2V 씬이 있을 때만 필요)
        anchor = ""
        if any(s.video_mode == "t2v" for s in video_scenes):
            anchor = self.generate_visual_anchor(
                title=title, body_summary=body_summary, mood=mood, post_id=post_id,
            )
            if anchor:
                logger.info("[prompt] 비주얼 앵커 생성 완료 (%d자)", len(anchor))

        vision_enabled = llm_backend_supports_vision()
        prev_shot: str | None = None
        brief_ok = 0
        brief_fail = 0

        for i, scene in enumerate(scenes):
            if getattr(scene, "video_mode", None) not in ("t2v", "i2v"):
                continue
            try:
                text_lines = [
                    line.get("text", "") if isinstance(line, dict) else str(line)
                    for line in scene.text_lines
                ]
                is_i2v = scene.video_mode == "i2v"

                image_brief: str | None = None
                if is_i2v and vision_enabled:
                    init_image = getattr(scene, "video_init_image", None)
                    if init_image:
                        image_brief = self.generate_image_brief(
                            Path(init_image), post_id=post_id, scene_index=i,
                        )
                        if image_brief is None:
                            brief_fail += 1
                            # 프록시 vision 미지원 추정 — 이 post의 잔여 vision 호출 생략
                            vision_enabled = False
                            logger.warning(
                                "[prompt] 씬 %d brief 실패 — post 내 vision 비활성", i,
                            )
                        else:
                            brief_ok += 1

                scene.video_prompt = self.generate_prompt(
                    text_lines=text_lines,
                    mood=mood,
                    title=title,
                    body_summary=body_summary,
                    has_init_image=is_i2v,
                    post_id=post_id,
                    scene_index=i,
                    duration_sec=getattr(scene, "estimated_tts_sec", 0.0),
                    visual_anchor=anchor,
                    image_brief=image_brief,
                    image_category=getattr(scene, "video_image_category", None),
                    prev_shot_type=prev_shot if not is_i2v else None,
                )
            except Exception as e:
                logger.error("[prompt] 씬 %d 프롬프트 생성 실패: %s", i, e)
                scene.video_prompt = None
                scene.video_prompt_simplified = None
                continue

            # 다음 T2V 씬의 샷 다양성용 프레이밍 추적
            if scene.video_mode == "t2v" and scene.video_prompt:
                shot = _extract_shot_type(scene.video_prompt)
                if shot:
                    prev_shot = shot

            # Phase 7 재시도용 simplified 프롬프트 미리 생성 (LLM 호출 제로 보장)
            # generate_prompt 성공 후 별도 예외 처리 — 실패 시 원본으로 폴백
            try:
                scene.video_prompt_simplified = self.simplify_prompt(
                    scene.video_prompt,
                    post_id=post_id,
                    scene_index=i,
                    visual_anchor=anchor,
                )
            except Exception as e:
                logger.warning("[prompt] 씬 %d simplified 생성 실패 — 원본으로 폴백: %s", i, e)
                scene.video_prompt_simplified = scene.video_prompt

            logger.info(
                "[prompt] 씬 %d 프롬프트 생성 완료 (%d자, simplified %d자)",
                i, len(scene.video_prompt),
                len(scene.video_prompt_simplified),
            )

        logger.info(
            "[prompt] batch 완료: 비디오씬=%d, 앵커=%s, brief 성공=%d/실패=%d",
            len(video_scenes), "있음" if anchor else "없음", brief_ok, brief_fail,
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
