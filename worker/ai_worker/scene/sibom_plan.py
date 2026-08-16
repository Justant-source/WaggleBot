"""again_spring sibom_plan helpers — materialize captions, map beats to scenes.

Does not select characters (AS owns that). Never falls back to metaphor PNGs.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Spec defaults (docs/shared/marketing/sibom-video-insertion.md §9)
SIBOM_PUNCH_SEC = 1.2
SIBOM_SHAKE_IDS = frozenset({"indignant", "stunned", "burst-crying", "two-argue"})
_BODY_ROLES = frozenset({"peak", "punch", "soft_fill"})
_VALID_SIZES = frozenset({"large", "small"})
_VALID_DWELLS = frozenset({"hold", "punch"})


def parse_sibom_plan(variant_config: dict | None) -> list[dict[str, Any]]:
    """Normalize ``sibom_plan`` / ``sibomPlan`` from variant_config into dict items."""
    cfg = variant_config if isinstance(variant_config, dict) else {}
    raw = cfg.get("sibom_plan")
    if raw is None:
        raw = cfg.get("sibomPlan")
    if not isinstance(raw, list):
        return []

    out: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        image_id = item.get("image_id") or item.get("imageId")
        if not isinstance(image_id, str) or not image_id.strip():
            continue
        role = str(item.get("role") or "punch").strip().lower()
        size = str(item.get("size") or ("large" if role in ("intro", "peak") else "small")).strip().lower()
        dwell = str(item.get("dwell") or ("hold" if role in ("intro", "peak") else "punch")).strip().lower()
        if size not in _VALID_SIZES:
            size = "large" if role in ("intro", "peak") else "small"
        if dwell not in _VALID_DWELLS:
            dwell = "hold" if role in ("intro", "peak") else "punch"
        beat_raw = item.get("beat_index", item.get("beatIndex", 0))
        try:
            beat_index = int(beat_raw)
        except (TypeError, ValueError):
            beat_index = 0
        caption = item.get("caption")
        if caption is None:
            caption = ""
        else:
            caption = str(caption)
        out.append({
            "role": role,
            "image_id": image_id.strip(),
            "caption": caption,
            "beat_index": beat_index,
            "size": size,
            "dwell": dwell,
        })
    return out


def _safe_filename(image_id: str, caption: str) -> str:
    import hashlib
    base = re.sub(r"[^a-zA-Z0-9_-]+", "_", image_id)[:48] or "sibom"
    cap_hash = hashlib.md5((caption or "").encode("utf-8")).hexdigest()[:8]
    return f"{base}_{cap_hash}.png"


def materialize_sibom_image(
    image_id: str,
    caption: str,
    cache_dir: Path,
) -> str | None:
    """Composite caption onto sprout PNG; return local path or None on failure."""
    try:
        from ai_worker.renderer.sibom_composite import composite_caption
    except ImportError:
        logger.warning("[sibom] sibom_composite unavailable — skip %s", image_id)
        return None

    cache_dir.mkdir(parents=True, exist_ok=True)
    out_path = cache_dir / _safe_filename(image_id, caption or "")
    if out_path.is_file():
        return str(out_path)

    try:
        img = composite_caption(image_id, caption or "")
        img.save(str(out_path), "PNG")
        return str(out_path)
    except Exception:
        logger.warning("[sibom] composite failed for id=%s", image_id, exc_info=True)
        return None


def resolve_sibom_intro_image(
    plan: list[dict[str, Any]],
    cache_dir: Path,
) -> tuple[str | None, dict[str, Any] | None]:
    """Return (path, plan_item) for first ``role=intro``; else (None, None) → cream+text."""
    for item in plan:
        if item.get("role") != "intro":
            continue
        path = materialize_sibom_image(item["image_id"], item.get("caption") or "", cache_dir)
        if path:
            return path, item
        # Missing asset → cream only (no metaphor fallback)
        return None, item
    return None, None


def apply_sibom_plan_to_body(
    body_scenes: list,
    plan: list[dict[str, Any]],
    cache_dir: Path,
) -> list:
    """Insert Sibomi as dedicated visual cuts after story screens.

    Story narration stays on text_only screens (up to 3 sentence-lines).
    Sibomi cuts carry the character + short situational caption only — they do
    not reuse the story text as cramped overlay copy.
    Comments/outro are not in body_scenes. Intro is handled separately.
    Never assigns metaphor assets.
    """
    if not body_scenes or not plan:
        return body_scenes

    from dataclasses import replace

    by_scene: dict[int, list[dict[str, Any]]] = {}
    n_story = len(body_scenes)
    for item in plan:
        role = item.get("role")
        if role not in _BODY_ROLES:
            continue
        beat = max(0, min(int(item.get("beat_index") or 0), max(n_story - 1, 0)))
        by_scene.setdefault(beat, []).append(item)

    out: list = []
    for index, scene in enumerate(body_scenes):
        out.append(scene)
        if getattr(scene, "block_type", "body") == "comment":
            continue
        for item in by_scene.get(index, []):
            path = materialize_sibom_image(
                item["image_id"], item.get("caption") or "", cache_dir,
            )
            if not path:
                continue
            role = item.get("role")
            dwell = item.get("dwell") or "punch"
            visual = replace(
                scene,
                type="image_only",
                text_lines=[],
                pre_split_lines=None,
                image_url=path,
                video_mode="static",
                sibom_role=role,
                sibom_size=item.get("size") or "small",
                sibom_dwell=dwell,
                sibom_image_id=item["image_id"],
                sibom_shake=item["image_id"] in SIBOM_SHAKE_IDS,
                dwell_sec=SIBOM_PUNCH_SEC if dwell == "punch" else getattr(scene, "dwell_sec", 4.0),
            )
            out.append(visual)

    body_scenes[:] = out
    return body_scenes


def sibom_cache_dir(post_id: int | None = None) -> Path:
    try:
        from config.settings import MEDIA_DIR
        base = Path(MEDIA_DIR) / "tmp" / "sibom"
    except Exception:
        base = Path("/tmp/wagglebot_sibom")
    return base / (str(post_id) if post_id is not None else "anon")
