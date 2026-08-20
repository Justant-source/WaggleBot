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


def split_story_lines(text: str) -> list[str]:
    """Split marketing narration into semantic lines (sentence → clause)."""
    normalized = " ".join((text or "").split())
    if not normalized:
        return []

    lines: list[str] = []
    for sentence in _SENTENCE_SPLIT.split(normalized):
        sentence = sentence.strip()
        if not sentence:
            continue
        lines.extend(_split_clauses(sentence))
    return [line for line in lines if line]


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
            buffer.append(scene)
            if len(buffer) >= 3:
                _flush()
        else:
            _flush()
            out.append(scene)

    _flush()
    return out


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
