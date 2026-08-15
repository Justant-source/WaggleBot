"""Hard quality gates for Again-Spring short-form marketing renders."""
from __future__ import annotations

import re
import subprocess
from copy import copy
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class MarketingQualityError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


@dataclass(frozen=True)
class MarketingRequirements:
    target_sec: float
    allowed_sec: float
    min_sibom: int
    platform: str


def requirements(site_code: str | None, cfg: dict[str, Any]) -> MarketingRequirements | None:
    if site_code != "again_spring" or not cfg.get("pre_scripted"):
        return None
    layout = str(cfg.get("platform_layout") or "").strip().lower()
    if layout == "reels_compact":
        return MarketingRequirements(30.0, 32.0, 4, "instagram_reels")
    if layout == "shorts_standard":
        return MarketingRequirements(45.0, 47.0, 5, "youtube_shorts")
    return None


def media_duration(path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        check=True, capture_output=True, text=True,
    )
    return float(result.stdout.strip())


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?…])\s+|(?<=요)\s+(?=[가-힣])|(?<=다)\s+(?=[가-힣])", text.strip())
    return [part.strip() for part in parts if part and part.strip()]


def shorten_script(script: Any, initial_duration: float, target_duration: float) -> tuple[Any, int, int]:
    """Deterministically keep hook/CTA and sentence-boundary body within target ratio."""
    original_chars = len(script.to_narration_text())
    if initial_duration <= target_duration:
        return script, original_chars, original_chars
    budget = max(1, int(original_chars * target_duration / initial_duration * 0.94))
    hook = str(script.hook or "").strip()
    closer = str(script.closer or "").strip()
    protected = len(hook) + len(closer)
    body_budget = max(0, budget - protected)
    out_body: list[dict[str, Any]] = []
    used = 0
    for item in list(script.body or []):
        lines = item.get("lines", []) if isinstance(item, dict) else [str(item)]
        for sentence in _sentences(" ".join(str(x) for x in lines)):
            if used and used + len(sentence) > body_budget:
                break
            out_body.append({"line_count": 1, "lines": [sentence]})
            used += len(sentence)
        if used >= body_budget:
            break
    if not out_body:
        raise MarketingQualityError("DURATION_SCRIPT_UNSHRINKABLE", "hook and CTA exceed the target duration budget")
    script.body = out_body
    return script, original_chars, len(script.to_narration_text())


def expand_body_scenes_at_sentence_boundaries(body_scenes: list[Any], minimum: int) -> list[Any]:
    """Split existing body scenes before placement; never duplicate narration text."""
    if len(body_scenes) >= minimum:
        return body_scenes
    expanded: list[Any] = []
    for scene in body_scenes:
        lines = list(getattr(scene, "text_lines", None) or [])
        fragments = _sentences(" ".join(str(x) for x in lines))
        if len(fragments) < 2:
            expanded.append(scene)
            continue
        for fragment in fragments:
            clone = copy(scene)
            clone.text_lines = [fragment]
            expanded.append(clone)
    return expanded
