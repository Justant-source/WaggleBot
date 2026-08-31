"""Again Spring short-form story line splitting and text_only packing.

SSOT: docs/shared/marketing/sibom-video-insertion.md §6.1 (Again-Spring repo).
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ai_worker.scene.director import SceneDecision

# Clause / connective endings — split *after* the marker (marker stays on the left chunk).
_CLAUSE_MARKERS: tuple[str, ...] = (
    "는데,",
    "는데",
    "지만,",
    "지만",
    "은데,",
    "은데",
    "ㄴ데,",
    "ㄴ데",
    "다가,",
    "다가",
    "보며",
    "하며",
    "으며",
)

# Longer markers first so e.g. "는데," wins over "는데".
_CLAUSE_MARKERS_SORTED = tuple(sorted(_CLAUSE_MARKERS, key=len, reverse=True))

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?…])\s+")

# 구어체 종결어미 — 이 프로젝트 나레이션은 마침표를 쓰지 않는다.
# 오분할을 피하려고 한 글자짜리(지·데·걸·야)는 뺐다("아버지 ", "그걸 " 같은 데서 끊긴다).
_SENTENCE_ENDINGS: tuple[str, ...] = (
    "습니다", "입니다", "겠습니다",
    "더라고", "더라", "거든", "잖아", "겠어", "겠네", "네요", "세요",
    "어요", "아요", "에요", "예요", "지요", "구요",
    "았어", "었어", "였어", "왔어", "갔어", "했어", "됐어", "봤어",
    "있어", "없어", "싶어", "같아", "몰라", "드라",
)
# 종결어미 뒤 공백에서 끊는다. 어미 길이가 제각각이라 lookbehind 는 쓸 수 없으므로
# (파이썬은 가변 길이 lookbehind 를 지원하지 않는다) 어미 뒤에 개행을 심고 그걸로 쪼갠다.
_ENDING_RE = re.compile(
    r"(" + "|".join(sorted(_SENTENCE_ENDINGS, key=len, reverse=True)) + r")\s+"
)


# 과거형 종결(…했어/…버렸어/…떠났어/…좋아졌어)은 어간이 무한히 많아 열거할 수 없다.
# 대신 "받침이 ㅆ 인 음절 + 어" 라는 형태 규칙으로 잡는다. 한글 음절 코드에서
# 종성 인덱스 20 이 ㅆ 이다.
_PAST_TENSE_RE = re.compile(r"([가-힣])(어요|어)(\s+)")
_SSANG_SIOT_JONGSEONG = 20


def _mark_past_tense(m: "re.Match[str]") -> str:
    stem = m.group(1)
    if (ord(stem) - 0xAC00) % 28 == _SSANG_SIOT_JONGSEONG:
        return stem + m.group(2) + "\n"
    return m.group(0)


def _split_by_endings(text: str) -> list[str]:
    marked = _ENDING_RE.sub(lambda m: m.group(1) + "\n", text)
    marked = _PAST_TENSE_RE.sub(_mark_past_tense, marked)
    return [chunk.strip() for chunk in marked.split("\n") if chunk.strip()]

# 한 화면이 감당할 글자 수. 캔버스 1080px·본문 폰트 기준 한 줄 ~22자,
# 표시 줄 수 상한이 3줄이라 물리적으로는 ~66자가 한계다.
# 다만 낭독 속도(약 10.2자/초) 기준 40자 ≈ 4초라, 호흡을 위해 그보다 낮게 잡는다.
_MAX_LINE_CHARS = 40

# 이보다 짧은 줄은 독립된 화면으로 두지 않는다.
# 기준을 15자로 잡았더니 "아버지 요즘 항암 투병 중이세요"(17자)처럼
# 한 줄짜리 화면이 4초씩 유지되며 화면의 95%가 비었다.
# 가용폭 900px·본문 52px 기준 표시 한 줄이 약 22자다. 22자를 넘겨야
# 두 줄로 감싸져 글 덩어리로 보이므로 24자를 하한으로 둔다.
_MIN_LINE_CHARS = 24
# 되붙일 때의 상한 — 가용폭 900px · 본문 52px · 표시 3줄이 감당하는 한계
_MERGE_CEILING = 66


def _absorb_short_lines(lines: list[str]) -> list[str]:
    """짧은 조각을 이웃 줄에 흡수시킨다.

    앞 줄에 붙이는 것을 우선하고(문장 흐름이 이어진다), 앞 줄이 이미 꽉 차
    있으면 뒤 줄 앞에 붙인다. 둘 다 안 되면 그대로 둔다 — 화면 하나를
    희생하더라도 글자가 잘리는 것보다는 낫다.
    """
    out: list[str] = []
    for line in lines:
        if out and len(line) < _MIN_LINE_CHARS and len(out[-1]) + 1 + len(line) <= _MERGE_CEILING:
            out[-1] = f"{out[-1]} {line}"
        else:
            out.append(line)
    # 앞에서 흡수하지 못한 짧은 줄(주로 첫 줄)은 뒤 줄로 넘긴다
    if len(out) >= 2 and len(out[0]) < _MIN_LINE_CHARS and len(out[0]) + 1 + len(out[1]) <= _MERGE_CEILING:
        out[1] = f"{out[0]} {out[1]}"
        out.pop(0)
    return out


# 상한 때문에 어쩔 수 없이 끊어야 할 때, 아무 띄어쓰기가 아니라
# 어미로 끝나는 어절 뒤를 고른다. 안 그러면 "밥을 따로 먹어 나 / 혼자 식탁에" 처럼
# 붙어 있어야 할 말이 갈라진다.
_SOFT_BREAK_RE = re.compile(r"(?:어|아|지|네|고|서|며|만|까|요|다)\s")


def _best_cut(text: str, limit: int) -> int:
    """limit 이하에서 끊기 좋은 위치를 찾는다. 없으면 -1."""
    best = -1
    for m in _SOFT_BREAK_RE.finditer(text):
        if m.end() > limit + 1:
            break
        best = m.end() - 1  # 공백 앞
    return best


def _enforce_max_chars(line: str, limit: int = _MAX_LINE_CHARS) -> list[str]:
    """상한을 넘는 줄을 단어 경계에서 잘라 여러 줄로 만든다.

    종결어미 탐지가 놓친 경우에도 화면이 반드시 넘어가게 하는 안전장치다.
    """
    line = line.strip()
    if len(line) <= limit:
        return [line] if line else []
    out: list[str] = []
    rest = line
    while len(rest) > limit:
        cut = _best_cut(rest, limit)
        if cut <= 0:
            cut = rest.rfind(" ", 0, limit + 1)
        if cut <= 0:
            cut = limit  # 공백이 없으면 어쩔 수 없이 글자 단위로 자른다
        out.append(rest[:cut].strip())
        rest = rest[cut:].strip()
    if rest:
        out.append(rest)
    return [x for x in out if x]


def split_story_lines(text: str) -> list[str]:
    """Split marketing narration into semantic lines (sentence → clause)."""
    normalized = " ".join((text or "").split())
    if not normalized:
        return []

    lines: list[str] = []
    for sentence in _SENTENCE_SPLIT.split(normalized):
        for chunk in _split_by_endings(sentence):
            chunk = chunk.strip()
            if not chunk:
                continue
            for clause in _split_clauses(chunk):
                lines.extend(_enforce_max_chars(clause))
    return _absorb_short_lines([line for line in lines if line])


def _split_clauses(sentence: str) -> list[str]:
    """Recursively split one sentence at the earliest clause marker."""
    sentence = sentence.strip()
    if not sentence:
        return []

    best_idx = -1
    best_len = 0
    for marker in _CLAUSE_MARKERS_SORTED:
        pos = 0
        while True:
            idx = sentence.find(marker, pos)
            if idx < 0:
                break
            end = idx + len(marker)
            if end < len(sentence):
                if best_idx < 0 or idx < best_idx or (idx == best_idx and len(marker) > best_len):
                    best_idx = idx
                    best_len = len(marker)
            pos = idx + 1

    if best_idx < 0:
        return [sentence]

    left = sentence[: best_idx + best_len].strip()
    right = sentence[best_idx + best_len :].strip()
    parts: list[str] = []
    if left:
        parts.append(left)
    if right:
        parts.extend(_split_clauses(right))
    return parts


def pack_undecorated_story_screens(scenes: list[SceneDecision]) -> list[SceneDecision]:
    """Merge adjacent plain ``text_only`` scenes into packs of up to 3 lines."""
    if not scenes:
        return scenes

    from ai_worker.scene.director import SceneDecision

    out: list[SceneDecision] = []
    buffer: list[SceneDecision] = []

    def _flush() -> None:
        nonlocal buffer
        if not buffer:
            return
        out.append(_merge_text_only_pack(buffer))
        buffer = []

    for scene in scenes:
        is_plain_text = scene.type == "text_only" and not getattr(scene, "sibom_role", None)
        if is_plain_text:
            # 글자 수 예산을 넘기면 먼저 비운다 — 개수만 세면 긴 줄 3개가
            # 한 화면에 뭉쳐 30초 넘게 멈춰 있는 화면이 만들어진다.
            projected = sum(len(_scene_text(x)) for x in buffer) + len(_scene_text(scene))
            if buffer and projected > _MAX_LINE_CHARS:
                _flush()
            buffer.append(scene)
            if len(buffer) >= 3:
                _flush()
        else:
            _flush()
            out.append(scene)

    _flush()
    return out


def _scene_text(scene: "SceneDecision") -> str:
    psl = getattr(scene, "pre_split_lines", None)
    return " ".join(psl or scene.text_lines or [])


def _merge_text_only_pack(scenes: list[SceneDecision]) -> SceneDecision:
    from ai_worker.scene.director import SceneDecision

    lines: list[str] = []
    for scene in scenes:
        psl = getattr(scene, "pre_split_lines", None)
        if psl:
            lines.extend(psl)
        else:
            lines.extend(scene.text_lines or [])
    template = scenes[0]
    return SceneDecision(
        type="text_only",
        text_lines=[" ".join(lines)],
        image_url=None,
        mood=template.mood,
        tts_emotion=template.tts_emotion,
        voice_override=template.voice_override,
        block_type=getattr(template, "block_type", "body"),
        author=getattr(template, "author", None),
        pre_split_lines=lines,
        video_mode=getattr(template, "video_mode", "static") or "static",
    )


def body_text_from_script(script: dict) -> str:
    """Join Again Spring script body blocks into one narration string."""
    parts: list[str] = []
    for item in script.get("body", []):
        if isinstance(item, dict):
            if item.get("type") == "comment":
                continue
            lines = item.get("lines") or []
            if lines:
                parts.append(" ".join(str(x) for x in lines if str(x).strip()))
            else:
                text = item.get("text")
                if text:
                    parts.append(str(text).strip())
        elif item:
            parts.append(str(item).strip())
    return " ".join(parts)


def build_body_scenes_from_script(
    script: dict,
    *,
    mood: str,
    tts_emotion: str,
    narrator_voice: str | None,
) -> list[SceneDecision]:
    """One ``text_only`` scene per semantic line (before sibom / pack)."""
    from ai_worker.scene.director import SceneDecision

    body_text = body_text_from_script(script)
    lines = split_story_lines(body_text)
    scenes: list[SceneDecision] = []
    for line in lines:
        scenes.append(
            SceneDecision(
                type="text_only",
                text_lines=[line],
                image_url=None,
                mood=mood,
                tts_emotion=tts_emotion,
                voice_override=narrator_voice,
                block_type="body",
                pre_split_lines=[line],
                video_mode="static",
            )
        )
    return scenes
