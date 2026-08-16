"""Again Spring story-text layout: sentence/clause lines.

Do not wrap on a 20/22-char window or subject/object particles.
Sibomi beats stay one clause + character; undecorated clauses pack up to 3.
"""
from __future__ import annotations

import re

STORY_LINES_PER_SCREEN = 3

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?…])\s+")
# Longer markers first so "는데," wins over "는데 ".
_CLAUSE_MARKERS = ("는데, ", "는데,", "는데 ", "지만, ", "지만,", "지만 ", "은데 ", "ㄴ데 ")


def split_story_lines(text: str) -> list[str]:
    """Split at sentence periods and clause endings (는데/지만). No mid-phrase wrap."""
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
        left = sentence[: pos + len(marker)].strip()
        right = sentence[pos + len(marker) :].strip()
        if left and right and len(left) >= 6:
            return _split_sentence(left) + _split_sentence(right)
    return [sentence]
