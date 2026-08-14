"""시봄이(Sibom) 캡션 합성 + 프레임 배치.

1단계: ``png/{id}.png`` 위에 catalog slot rect 안으로 캡션을 그린다.
2단계: 그 RGBA 결과를 1080×1920 프레임에 large/small 로 붙인다.

Director 배선은 이 모듈 범위 밖 — 공개 API만 제공한다.

  composite_caption(image_id, caption) -> Image (820×820 or taller RGBA)
  paste_on_frame(frame, img, size=\"large\"|\"small\") -> Image

small 배치: 스케일 0.40, **우하단** 앵커 (마진 40px).
large 배치: (90, 550) @ scale 1.0.

폰트: WaggleBot 기본과 동일하게 ``NotoSansKR-Bold`` 우선
(``assets/fonts`` → 호스트/시스템 한글 Bold → fc-list).
"""
from __future__ import annotations

import json
import logging
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Literal, Optional

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

SizeMode = Literal["large", "small"]

# Catalog canvas / frame placement (docs/shared/marketing/sibom-video-insertion.md §6·§9)
SIBOM_CANVAS = 820
FRAME_W = 1080
FRAME_H = 1920
LARGE_XY = (90, 550)
LARGE_SCALE = 1.0
SMALL_SCALE = 0.40
SMALL_MARGIN_XY = (40, 40)  # bottom-right inset from frame edges
DEFAULT_INK = "#5C4030"
DEFAULT_FONT_SIZE = 80
# Right/left inset for multi-line caption extension.
# Layout pad owns the visible margin; wrap inset only covers measure error.
CAPTION_OUTER_PADDING = 44
CAPTION_WRAP_INSET = 8
BOLD_FONT_CANDIDATES = (
    "NotoSansKR-Bold.ttf",
    "NotoSansCJKkr-Bold.otf",
    "NotoSansKR-Bold-renamed.ttf",
    "NanumGothicBold.ttf",
)


def _candidate_asset_roots() -> list[Path]:
    """Possible ASSETS roots: settings → host checkout → Docker /app mount."""
    roots: list[Path] = []
    try:
        from config.settings import ASSETS_DIR

        roots.append(Path(ASSETS_DIR))
    except Exception:
        pass
    here = Path(__file__).resolve()
    # Host: WaggleBot/worker/ai_worker/renderer → WaggleBot/assets
    roots.append(here.parents[3] / "assets")
    # Docker: /app/ai_worker/renderer → /app/assets
    roots.append(here.parents[2] / "assets")
    # de-dupe, preserve order
    seen: set[Path] = set()
    out: list[Path] = []
    for r in roots:
        rp = r.resolve() if r.exists() else r
        if rp not in seen:
            seen.add(rp)
            out.append(r)
    return out


def default_sprouts_dir() -> Path:
    """``assets/sprouts`` (Docker: ``/app/assets/sprouts``)."""
    for root in _candidate_asset_roots():
        sprouts = root / "sprouts"
        if (sprouts / "catalog.json").exists():
            return sprouts
    return _candidate_asset_roots()[0] / "sprouts"


def default_font_dir() -> Path:
    for root in _candidate_asset_roots():
        fonts = root / "fonts"
        if fonts.is_dir():
            return fonts
    return _candidate_asset_roots()[0] / "fonts"


@lru_cache(maxsize=1)
def load_catalog(sprouts_dir: Optional[str] = None) -> dict:
    root = Path(sprouts_dir) if sprouts_dir else default_sprouts_dir()
    path = root / "catalog.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def clear_catalog_cache() -> None:
    load_catalog.cache_clear()


def get_image_meta(image_id: str, catalog: Optional[dict] = None) -> dict:
    cat = catalog if catalog is not None else load_catalog()
    for item in cat.get("images", []):
        if item.get("id") == image_id:
            return item
    raise KeyError(f"unknown sibom image_id: {image_id!r}")


def get_slot_preset(slot: str, catalog: Optional[dict] = None) -> dict:
    cat = catalog if catalog is not None else load_catalog()
    presets = cat.get("presets") or {}
    if slot not in presets:
        raise KeyError(f"unknown sibom slot preset: {slot!r}")
    return presets[slot]


def resolve_bold_font_path(font_dir: Optional[Path] = None) -> Path:
    """Return the first usable Korean bold font path.

    Preference matches existing WaggleBot renderer usage (NotoSansKR-Bold).
    """
    fdir = Path(font_dir) if font_dir else default_font_dir()
    candidates: list[Path] = [fdir / name for name in BOLD_FONT_CANDIDATES]
    home = Path.home() / ".local" / "share" / "fonts"
    candidates.extend(
        [
            home / "NotoSansKR-Bold-renamed.ttf",
            home / "NotoSansCJKkr-Bold.otf",
            home / "NotoSansKR-Bold.ttf",
            Path("/usr/share/fonts/truetype/noto/NotoSansKR-Bold.ttf"),
            Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"),
            Path("/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf"),
            Path("/usr/share/fonts/nanum/NanumGothicBold.ttf"),
        ]
    )
    for path in candidates:
        if path.exists():
            try:
                ImageFont.truetype(str(path), DEFAULT_FONT_SIZE)
                return path
            except Exception:
                continue
    try:
        result = subprocess.run(
            ["fc-list", ":lang=ko", "--format=%{file}\n"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        for line in result.stdout.splitlines():
            p = Path(line.strip())
            if not p.exists():
                continue
            name_u = p.name.upper()
            if "BOLD" not in name_u and "BLACK" not in name_u:
                continue
            try:
                ImageFont.truetype(str(p), DEFAULT_FONT_SIZE)
                return p
            except Exception:
                continue
        # any Korean font as last resort
        for line in result.stdout.splitlines():
            p = Path(line.strip())
            if p.exists():
                try:
                    ImageFont.truetype(str(p), DEFAULT_FONT_SIZE)
                    return p
                except Exception:
                    continue
    except Exception:
        pass
    raise FileNotFoundError(
        "No Korean-capable bold font found for sibom caption compositing"
    )


def _load_font(size: int, font_dir: Optional[Path] = None) -> ImageFont.FreeTypeFont:
    path = resolve_bold_font_path(font_dir)
    font = ImageFont.truetype(str(path), size)
    # Variable-font weight hint (same idea as layout._apply_vf_weight)
    try:
        font.set_variation_by_name("Bold")
    except Exception:
        pass
    return font


def _font_w(font: ImageFont.ImageFont, text: str) -> float:
    """Ink-aware width; tiny slack only (pad owns the visible right margin)."""
    if not text:
        return 0.0
    try:
        bbox = font.getbbox(text)
        w = float(bbox[2] - bbox[0])
    except Exception:
        try:
            w = float(font.getlength(text))  # type: ignore[attr-defined]
        except Exception:
            bbox = font.getbbox(text)
            w = float(bbox[2] - bbox[0])
    return w * 1.01


def _wrap_to_width(text: str, font: ImageFont.ImageFont, max_width: int) -> list[str]:
    """Wrap at Korean eojeol (space-delimited word) boundaries only.

    Captions are intentionally never split inside a word.  A single word that
    exceeds *max_width* is therefore returned intact; the catalog's short
    caption limit keeps that exceptional case out of normal rendering.
    """
    text = (text or "").strip()
    if not text:
        return []
    if _font_w(font, text) <= max_width:
        return [text]

    words = text.split()
    lines: list[str] = []
    current = ""

    for word in words:
        candidate = f"{current} {word}" if current else word
        if _font_w(font, candidate) <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            # Do not fall back to character-level wrapping: Korean captions
            # must not be split into fragments such as "갑자" / "기".
            current = word
    if current:
        lines.append(current)
    return lines


def _caption_metrics(
    draw: ImageDraw.ImageDraw,
    lines: list[str],
    font: ImageFont.ImageFont,
) -> tuple[list[tuple[str, int, int, int]], int, int]:
    """Return text metrics, total height, and the inter-line gap."""
    metrics: list[tuple[str, int, int, int]] = []
    total_h = 0
    line_gap = max(4, int(getattr(font, "size", DEFAULT_FONT_SIZE) * 0.12))
    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        metrics.append((line, tw, th, bbox[1]))
        total_h += th
        if i:
            total_h += line_gap
    return metrics, total_h, line_gap


def _draw_caption_lines(
    draw: ImageDraw.ImageDraw,
    lines: list[str],
    font: ImageFont.ImageFont,
    rect: list[int] | tuple[int, int, int, int],
    color: str,
) -> None:
    """Center pre-wrapped caption lines inside *rect*."""
    if not lines:
        return
    x, y, w, h = (int(v) for v in rect)
    metrics, total_h, line_gap = _caption_metrics(draw, lines, font)
    cy = y + max(0, (h - total_h) // 2)
    for i, (line, tw, th, ascent) in enumerate(metrics):
        tx = x + max(0, (w - tw) // 2)
        draw.text((tx, cy - ascent), line, font=font, fill=color)
        cy += th + (line_gap if i < len(metrics) - 1 else 0)


def composite_caption(
    image_id: str,
    caption: str,
    *,
    sprouts_dir: Optional[Path] = None,
    font_dir: Optional[Path] = None,
    catalog: Optional[dict] = None,
) -> Image.Image:
    """Open ``png/{id}.png`` and draw *caption* into the catalog slot rect.

    The character PNG is always retained as its original square region.  A
    multi-line caption is rendered in a padded extension beneath it, so the
    complete composite may be rectangular without scaling, cropping, or
    distorting the character art. Empty caption leaves the PNG unchanged
    (character only) — useful for fallback chain step 2.
    """
    root = Path(sprouts_dir) if sprouts_dir else default_sprouts_dir()
    cat = catalog if catalog is not None else load_catalog(str(root))
    meta = get_image_meta(image_id, cat)
    slot = meta.get("slot") or "bottom"
    preset = get_slot_preset(slot, cat)

    png_path = root / "png" / f"{image_id}.png"
    if not png_path.exists():
        raise FileNotFoundError(f"sibom png missing: {png_path}")

    img = Image.open(png_path).convert("RGBA")
    if caption:
        font_size = int(preset.get("font_size") or DEFAULT_FONT_SIZE)
        color = str(preset.get("color") or cat.get("palette", {}).get("ink") or DEFAULT_INK)
        font = _load_font(font_size, font_dir)
        _, _, slot_w, _ = (int(v) for v in preset["rect"])
        lines = _wrap_to_width(caption, font, max(1, slot_w - CAPTION_WRAP_INSET))

        if len(lines) <= 1:
            draw = ImageDraw.Draw(img)
            _draw_caption_lines(draw, lines, font, preset["rect"], color)
            return img

        # The PNG itself remains a 1:1 character region at the top, pixel-for-
        # pixel unchanged (including its transparent corners) — the extended
        # canvas starts fully transparent and only the *new* band below the
        # original gets cream-filled, so alpha-compositing the character on
        # top never bleeds cream into its transparent background.
        measure = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
        _, caption_h, _ = _caption_metrics(measure, lines, font)
        caption_w = img.width - 2 * CAPTION_OUTER_PADDING
        cream = (255, 248, 240, 255)  # #FFF8F0
        extended = Image.new(
            "RGBA",
            (
                img.width,
                img.height + CAPTION_OUTER_PADDING + caption_h + CAPTION_OUTER_PADDING,
            ),
            (0, 0, 0, 0),
        )
        # Direct paste (no blend): copies RGBA verbatim, so the original square
        # region — transparent corners included — stays byte-identical.
        extended.paste(img, (0, 0))
        extended.paste(cream, (0, img.height, img.width, extended.height))
        draw = ImageDraw.Draw(extended)
        _draw_caption_lines(
            draw,
            lines,
            font,
            (CAPTION_OUTER_PADDING, img.height + CAPTION_OUTER_PADDING, caption_w, caption_h),
            color,
        )
        return extended
    return img


def paste_on_frame(
    frame: Image.Image,
    img: Image.Image,
    size: SizeMode = "large",
    *,
    large_xy: tuple[int, int] = LARGE_XY,
    large_scale: float = LARGE_SCALE,
    small_scale: float = SMALL_SCALE,
    small_margin: tuple[int, int] = SMALL_MARGIN_XY,
) -> Image.Image:
    """Paste a captioned sibom image onto a (typically 1080×1920) frame.

    - ``large``: top-left at *large_xy* (default 90,550), scale 1.0
    - ``small``: scale 0.40, **bottom-right** anchor with *small_margin*

    Returns an RGBA frame (converts *frame* if needed). Does not mutate the
    original if mode conversion is required; otherwise pastes onto a copy.
    """
    base = frame.convert("RGBA").copy()
    overlay = img.convert("RGBA")

    if size == "large":
        scale = large_scale
        if scale != 1.0:
            nw = max(1, int(overlay.width * scale))
            nh = max(1, int(overlay.height * scale))
            overlay = overlay.resize((nw, nh), Image.Resampling.LANCZOS)
        xy = large_xy
    elif size == "small":
        scale = small_scale
        nw = max(1, int(overlay.width * scale))
        nh = max(1, int(overlay.height * scale))
        overlay = overlay.resize((nw, nh), Image.Resampling.LANCZOS)
        mx, my = small_margin
        xy = (base.width - overlay.width - mx, base.height - overlay.height - my)
    else:
        raise ValueError(f"size must be 'large' or 'small', got {size!r}")

    base.alpha_composite(overlay, xy)
    return base


def make_cream_frame(
    size: tuple[int, int] = (FRAME_W, FRAME_H),
    color: tuple[int, int, int, int] = (251, 243, 236, 255),
) -> Image.Image:
    """Blank cream 9:16 frame for smoke tests / intro fallback."""
    return Image.new("RGBA", size, color)


# ---------------------------------------------------------------------------
# Smoke / CLI
# ---------------------------------------------------------------------------

def _smoke(out_path: Path | None = None) -> Path:
    out = out_path or Path("/tmp/sibom_smoke_frame.png")
    out.parent.mkdir(parents=True, exist_ok=True)
    captioned = composite_caption("waiting-reply", "읽씹 3일차")
    frame = make_cream_frame()
    composed = paste_on_frame(frame, captioned, size="large")
    # also stamp a small sticker so both modes are visible
    small = composite_caption("indignant", "왜 나만")
    composed = paste_on_frame(composed, small, size="small")
    composed.convert("RGB").save(out)
    font_used = resolve_bold_font_path()
    print(f"wrote {out}")
    print(f"font  {font_used}")
    return out


if __name__ == "__main__":
    import sys

    # Allow `python3 ai_worker/renderer/sibom_composite.py` without package __init__.
    _worker = Path(__file__).resolve().parents[2]
    _repo = Path(__file__).resolve().parents[3]
    for p in (_worker, _repo):
        s = str(p)
        if s not in sys.path:
            sys.path.insert(0, s)

    dest = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/sibom_smoke_frame.png")
    _smoke(dest)
