"""Again Spring story-text layout: sentence lines, max 3 per screen.

Story narration is not squeezed into the Sibomi caption slot. Long copy becomes
text_only screens; Sibomi keeps short situational captions on its own cuts.
"""
from __future__ import annotations

import re

# One on-screen story block. Long enough for a Korean clause; short enough that
# a 3-block screen still reads. Not the old max_chars=20 wrap window.
STORY_LINE_MAX = 22
STORY_LINES_PER_SCREEN = 3

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?…])\s+")
_CLAUSE_MARKERS = ("는데 ", "지만 ", "은데 ", "ㄴ데 ")


def split_story_lines(text: str) -> list[str]:
    """Split story copy into display lines at sentence/clause boundaries.

    Periods are always honored (no "must be past 60% of the window" rule).
    Remaining long sentences wrap on spaces only after that.
    """
    raw = " ".join((text or "").split())
    if not raw:
        return []

    sentences = [part.strip() for part in _SENTENCE_SPLIT.split(raw) if part.strip()]
    lines: list[str] = []
    for sentence in sentences:
        lines.extend(_split_sentence(sentence))
    return lines


def pack_story_screens(lines: list[str], per_screen: int = STORY_LINES_PER_SCREEN) -> list[list[str]]:
    """Group display lines into screens of at most ``per_screen`` blocks."""
    if per_screen < 1:
        per_screen = STORY_LINES_PER_SCREEN
    screens: list[list[str]] = []
    buf: list[str] = []
    for line in lines:
        if not line:
            continue
        buf.append(line)
        if len(buf) >= per_screen:
            screens.append(buf)
            buf = []
    if buf:
        screens.append(buf)
    return screens


def _split_sentence(sentence: str) -> list[str]:
    for marker in _CLAUSE_MARKERS:
        pos = sentence.find(marker)
        if pos <= 0:
            continue
        cut = pos + len(marker) - 1  # keep the clause ending, drop trailing space
        left = sentence[: cut + 1].strip()
        right = sentence[cut + 1 :].strip()
        if left and right and len(left) >= 6:
            return _split_sentence(left) + _split_sentence(right)

    # Subject/object particles: keep a readable clause on its own line.
    for marker, min_left, min_right, skip_right_prefix in (
        ("가 ", 10, 8, "다더고서"),
        ("를 ", 8, 8, ""),
        ("을 ", 8, 8, ""),
    ):
        start = 0
        while True:
            pos = sentence.find(marker, start)
            if pos < 0:
                break
            left = sentence[: pos + 1].strip()  # include 가/를/을
            right = sentence[pos + len(marker) :].strip()
            if (
                len(left) >= min_left
                and len(right) >= min_right
                and (not skip_right_prefix or right[0] not in skip_right_prefix)
            ):
                return _split_sentence(left) + _split_sentence(right)
            start = pos + 1
    return _wrap_if_needed(sentence)


def _wrap_if_needed(text: str) -> list[str]:
    if len(text) <= STORY_LINE_MAX:
        return [text]
    window = text[:STORY_LINE_MAX]
    pos = window.rfind(" ")
    if pos <= 0:
        return [text[:STORY_LINE_MAX], *(_wrap_if_needed(text[STORY_LINE_MAX:].strip()) if text[STORY_LINE_MAX:].strip() else [])]
    left = text[:pos].strip()
    right = text[pos:].strip()
    return [left] + (_wrap_if_needed(right) if right else [])
