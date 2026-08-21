"""시봄이 캡션 합성 단위 테스트 (패키지 __init__ / dotenv 없이 로드)."""
import importlib.util
import sys
from pathlib import Path

import pytest
from PIL import Image

pytestmark = pytest.mark.unit

_MOD_PATH = (
    Path(__file__).resolve().parents[1] / "ai_worker" / "renderer" / "sibom_composite.py"
)


def _load_mod():
    name = "sibom_composite_under_test"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, _MOD_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


sibom = _load_mod()

_SPROUTS = sibom.default_sprouts_dir()


def _require_assets() -> None:
    if not (_SPROUTS / "catalog.json").exists():
        pytest.skip(f"sprouts catalog missing: {_SPROUTS}")
    if not (_SPROUTS / "png" / "waiting-reply.png").exists():
        pytest.skip("sprouts png assets missing")


def test_catalog_loads_60_images():
    _require_assets()
    cat = sibom.load_catalog(str(_SPROUTS))
    assert cat["images_in_batch"] == 60
    assert len(cat["images"]) == 60
    assert "bottom" in cat["presets"]
    assert all(preset["maxChars"] == 10 for preset in cat["presets"].values())
    assert all(item["maxChars"] == 10 for item in cat["images"])
    assert all(
        len(text) <= 10
        for item in cat["images"]
        for text in [item["caption"], *item["alt_captions"]]
    )
    meta = sibom.get_image_meta("waiting-reply", cat)
    assert meta["slot"] == "bottom"


def test_resolve_bold_font():
    path = sibom.resolve_bold_font_path()
    assert path.exists()
    assert path.suffix.lower() in {".ttf", ".otf", ".ttc"}


def test_composite_caption_rgba_and_size():
    _require_assets()
    img = sibom.composite_caption("waiting-reply", "읽씹 3일차", sprouts_dir=_SPROUTS)
    assert img.mode == "RGBA"
    assert img.size == (sibom.SIBOM_CANVAS, sibom.SIBOM_CANVAS)


def test_wraps_captions_at_eojeol_boundaries_only():
    font = sibom._load_font(80)
    max_width = int(sibom._font_w(font, "갑자기")) + 1

    assert sibom._wrap_to_width("갑자기 너무 속상해", font, max_width) == [
        "갑자기",
        "너무",
        "속상해",
    ]


def test_multiline_caption_extends_below_unchanged_square_character():
    _require_assets()
    raw = Image.open(_SPROUTS / "png" / "waiting-reply.png").convert("RGBA")
    out = sibom.composite_caption(
        "waiting-reply",
        "갑자기정말 너무속상해",
        sprouts_dir=_SPROUTS,
    )

    assert out.width == sibom.SIBOM_CANVAS
    assert out.height > sibom.SIBOM_CANVAS
    assert out.crop((0, 0, raw.width, raw.height)).tobytes() == raw.tobytes()


def _first_opaque_xy(img: Image.Image, alpha_min: int = 200) -> tuple[int, int]:
    px = img.load()
    w, h = img.size
    for y in range(0, h, 4):
        for x in range(0, w, 4):
            if px[x, y][3] >= alpha_min:
                return x, y
    raise AssertionError("no opaque pixel found")


def test_composite_empty_caption_keeps_pixels():
    _require_assets()
    raw = Image.open(_SPROUTS / "png" / "waiting-reply.png").convert("RGBA")
    out = sibom.composite_caption("waiting-reply", "", sprouts_dir=_SPROUTS)
    assert out.tobytes() == raw.tobytes()


def test_paste_large_at_expected_origin():
    _require_assets()
    captioned = sibom.composite_caption(
        "waiting-reply", "읽씹 3일차", sprouts_dir=_SPROUTS
    )
    ox, oy = _first_opaque_xy(captioned)
    frame = sibom.make_cream_frame()
    out = sibom.paste_on_frame(frame, captioned, size="large")
    assert out.size == (sibom.FRAME_W, sibom.FRAME_H)
    cream = (251, 243, 236, 255)
    assert out.getpixel((90 + ox, 550 + oy)) != cream


def test_paste_small_bottom_right():
    _require_assets()
    captioned = sibom.composite_caption("indignant", "왜 나만", sprouts_dir=_SPROUTS)
    ox, oy = _first_opaque_xy(captioned)
    frame = sibom.make_cream_frame()
    out = sibom.paste_on_frame(frame, captioned, size="small")
    scaled_w = int(sibom.SIBOM_CANVAS * sibom.SMALL_SCALE)
    scaled_h = int(sibom.SIBOM_CANVAS * sibom.SMALL_SCALE)
    left = sibom.FRAME_W - 40 - scaled_w
    top = sibom.FRAME_H - 40 - scaled_h
    sx = left + int(ox * sibom.SMALL_SCALE)
    sy = top + int(oy * sibom.SMALL_SCALE)
    cream = (251, 243, 236, 255)
    assert out.getpixel((sx, sy)) != cream
    # sticker must sit in the bottom-right quadrant
    assert left > sibom.FRAME_W // 2
    assert top > sibom.FRAME_H // 2


def test_unknown_id_raises():
    _require_assets()
    with pytest.raises(KeyError):
        sibom.composite_caption("not-a-real-sibom", "x", sprouts_dir=_SPROUTS)
