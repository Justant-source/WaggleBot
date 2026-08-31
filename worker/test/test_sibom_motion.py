"""시봄이 모션(팝인·숨쉬기·셰이크) 단위 테스트.

test_tts_sync.py 관례: 렌더러 내부 함수를 직접 임포트, ffmpeg 실행 없음.
"""
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

pytestmark = pytest.mark.unit

from ai_worker.renderer.layout import (
    _attach_sibom_motion,
    _compose_sibom_into_slot,
    _paste_rounded,
    _fit_cover,
    _sibom_breathe_scale,
    _sibom_hold_segments,
    _sibom_pop_progress,
    _sibom_shake_offset,
    _write_sibom_breathe_frames,
    _write_sibom_punch_frames,
    _SIBOM_BREATHE_FRAMES,
    _SIBOM_PUNCH_POP_FRAMES,
)


# ── 타임라인 조립 (순수, Path만 다룸) ──────────────────────────────────

def _fake_paths(prefix: str, n: int) -> list[Path]:
    return [Path(f"/tmp/{prefix}_{i:02d}.png") for i in range(n)]


def test_hold_dwell_tiles_breathing_cycle():
    from ai_worker.renderer.layout import _build_visual_timeline, _SIBOM_PUNCH_SEC, _SIBOM_BREATHE_CYCLE_SEC

    punch = _fake_paths("punch", 12)
    loop = _fake_paths("breathe", 16)
    plan = [{"sent_idx": 0, "sibom_punch_paths": punch, "sibom_loop_paths": loop}]
    frame_paths = [Path("/tmp/frame_000.png")]
    durations = [6.0]

    timeline = _build_visual_timeline(frame_paths, plan, durations)

    # 처음 12개는 펀치, 각 1.2/12초
    per_punch = _SIBOM_PUNCH_SEC / len(punch)
    for i in range(12):
        assert timeline[i][0] == punch[i]
        assert timeline[i][1] == pytest.approx(per_punch)

    # 나머지는 숨쉬기 루프가 순서대로 반복
    hold = 6.0 - _SIBOM_PUNCH_SEC
    per_loop = _SIBOM_BREATHE_CYCLE_SEC / len(loop)
    loop_entries = timeline[12:]
    assert loop_entries[0][0] == loop[0]
    assert loop_entries[1][0] == loop[1]
    assert sum(d for _, d in timeline) == pytest.approx(6.0)


def test_punch_dwell_holds_last_entrance_frame():
    from ai_worker.renderer.layout import _build_visual_timeline, _SIBOM_PUNCH_SEC

    punch = _fake_paths("punch", 12)
    plan = [{"sent_idx": 0, "sibom_punch_paths": punch}]  # sibom_loop_paths 없음
    frame_paths = [Path("/tmp/frame_000.png")]
    durations = [3.0]

    timeline = _build_visual_timeline(frame_paths, plan, durations)

    assert len(timeline) == 13  # 12 punch + 마지막 프레임 정지 유지 1개
    assert timeline[-1][0] == punch[-1]
    assert timeline[-1][1] == pytest.approx(3.0 - _SIBOM_PUNCH_SEC)


def test_duration_shorter_than_punch_budget():
    from ai_worker.renderer.layout import _build_visual_timeline

    punch = _fake_paths("punch", 12)
    plan = [{"sent_idx": 0, "sibom_punch_paths": punch}]
    frame_paths = [Path("/tmp/frame_000.png")]
    durations = [0.5]

    timeline = _build_visual_timeline(frame_paths, plan, durations)

    assert len(timeline) == 12
    assert sum(d for _, d in timeline) == pytest.approx(0.5)


def test_non_sibom_entry_unchanged():
    from ai_worker.renderer.layout import _build_visual_timeline

    plan = [{"sent_idx": 0}]
    frame_paths = [Path("/tmp/frame_000.png")]
    durations = [4.0]

    timeline = _build_visual_timeline(frame_paths, plan, durations)

    assert timeline == [(Path("/tmp/frame_000.png"), 4.0)]


# ── 모션 수식 (순수 함수) ─────────────────────────────────────────────

def test_breathe_scale_is_seamless_sine():
    assert _sibom_breathe_scale(0, 16) == pytest.approx(1.0)
    assert _sibom_breathe_scale(8, 16) == pytest.approx(1.0, abs=1e-9)
    for i in range(16):
        s = _sibom_breathe_scale(i, 16)
        assert abs(s - 1.0) <= 0.03 + 1e-9


def test_shake_settles_to_zero():
    assert _sibom_shake_offset(1.0, 10) == (0, 0)
    dxs = [abs(_sibom_shake_offset(i / 20, 10)[0]) for i in range(21)]
    assert max(dxs) <= 10
    assert any(d > 0 for d in dxs[:7])  # 초반부에는 흔들림이 있어야 함


def test_pop_progress_eases_out():
    n = 12
    assert _sibom_pop_progress(0, n) == pytest.approx(0.0)
    assert _sibom_pop_progress(n - 1, n) == pytest.approx(1.0)
    vals = [_sibom_pop_progress(i, n) for i in range(n)]
    assert all(b >= a for a, b in zip(vals, vals[1:]))  # 단조 증가
    for i in range(1, n - 1):
        t = i / (n - 1)
        assert vals[i] > t  # ease-out: 항상 선형보다 앞서 나감


# ── 합성기 (PIL, 합성 자산) ────────────────────────────────────────────

def _make_plate(w=1080, h=1920, color=(255, 248, 240, 255)) -> Image.Image:
    return Image.new("RGBA", (w, h), color)


def _make_sprite(size=820) -> Image.Image:
    """캐릭터 대역 — 원형 불투명 + 투명 모서리(실제 시봄이 PNG와 동일 성질)."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([40, 40, size - 40, size - 40], fill=(200, 120, 90, 255))
    return img


def test_neutral_transform_matches_static_paste():
    plate = _make_plate()
    sprite = _make_sprite()
    rect = (138, 700, 804, 804)
    radius = 20

    composed = _compose_sibom_into_slot(plate, sprite, rect, radius)

    x, y, w, h = rect
    expected_tile = _paste_rounded(
        plate.convert("RGB").crop((x, y, x + w, y + h)),
        _fit_cover(sprite, w, h),
        0, 0, radius,
    )
    expected = plate.convert("RGB").copy()
    expected.paste(expected_tile, (x, y))

    assert composed.tobytes() == expected.tobytes()


def test_breathe_frame_zero_matches_last_punch_frame(tmp_path):
    plate = _make_plate()
    sprite = _make_sprite()
    rect = (138, 700, 804, 804)
    radius = 20

    punch = _write_sibom_punch_frames(plate, sprite, rect, radius, tmp_path, 0)
    breathe = _write_sibom_breathe_frames(plate, sprite, rect, radius, tmp_path, 0)

    assert Image.open(breathe[0]).tobytes() == Image.open(punch[-1]).tobytes()


def test_shake_stays_inside_slot(tmp_path):
    plate = _make_plate()
    sprite = _make_sprite()
    rect = (138, 700, 804, 804)
    radius = 20

    frames = _write_sibom_punch_frames(plate, sprite, rect, radius, tmp_path, 0, shake=True)

    x, y, w, h = rect
    plate_rgb = plate.convert("RGB")
    for p in frames:
        img = Image.open(p)
        # 슬롯 바깥 한 점(코너에서 충분히 떨어진 곳)은 plate와 동일해야 함
        assert img.getpixel((10, 10)) == plate_rgb.getpixel((10, 10))
        assert img.getpixel((x + w + 50, y + h + 50)) == plate_rgb.getpixel((x + w + 50, y + h + 50))


def test_no_shake_when_flag_false(tmp_path):
    plate = _make_plate()
    sprite = _make_sprite()
    rect = (138, 700, 804, 804)
    radius = 20

    a = _write_sibom_punch_frames(plate, sprite, rect, radius, tmp_path, 0, shake=False)
    b = _write_sibom_punch_frames(plate, sprite, rect, radius, tmp_path, 1, shake=False)

    for pa, pb in zip(a, b):
        assert Image.open(pa).tobytes() == Image.open(pb).tobytes()


def test_motion_failure_falls_back_to_static(monkeypatch, tmp_path):
    import ai_worker.renderer.layout as layout_mod

    def _boom(*a, **k):
        raise RuntimeError("forced failure")

    monkeypatch.setattr(layout_mod, "_write_sibom_punch_frames", _boom)

    entry = {"sibom_role": "punch", "sibom_dwell": "punch"}
    plate = _make_plate()
    sprite = _make_sprite()
    rect = (138, 700, 804, 804)

    _attach_sibom_motion(entry, plate, sprite, rect, 20, tmp_path, 0)

    assert "sibom_punch_paths" not in entry
    assert "sibom_loop_paths" not in entry


# ── 캡션 크롭 회귀(2026-08-14) ─────────────────────────────────────────

def _make_captioned_sprite(w=820, top_h=820, caption_h=247) -> Image.Image:
    """composite_caption()이 다줄 캡션일 때 만드는 세로 확장 스프라이트 대역.
    상단(top_h)엔 원형 캐릭터, 하단(caption_h)엔 캡션 밴드 색상 마커."""
    img = Image.new("RGBA", (w, top_h + caption_h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([40, 40, w - 40, top_h - 40], fill=(200, 120, 90, 255))
    d.rectangle([0, top_h, w, top_h + caption_h], fill=(255, 248, 240, 255))
    d.rectangle([80, top_h + 60, w - 80, top_h + 160], fill=(0x5C, 0x40, 0x30, 255))
    return img


def test_tall_captioned_sprite_not_cropped_by_slot():
    """bubble 슬롯 다줄 캡션(세로 확장 스프라이트)이 정사각 카드 슬롯에
    들어갈 때 cover로 크롭되면 캡션 밴드가 사라진다 — contain 폴백으로
    끝까지 보존돼야 한다."""
    plate = _make_plate()
    sprite = _make_captioned_sprite()
    rect = (138, 700, 804, 804)
    radius = 20

    composed = _compose_sibom_into_slot(plate, sprite, rect, radius)

    x, y, w, h = rect
    region = composed.crop((x, y, x + w, y + h))
    px = region.load()
    ink = (0x5C, 0x40, 0x30)

    def has_ink(y0, y1):
        for yy in range(int(h * y0), int(h * y1)):
            for xx in range(0, w, 4):
                r, g, b = px[xx, yy]
                if abs(r - ink[0]) < 30 and abs(g - ink[1]) < 30 and abs(b - ink[2]) < 30:
                    return True
        return False

    assert has_ink(0.5, 1.0), "캡션 밴드(하단)가 cover 크롭으로 사라짐"


def test_square_sprite_still_uses_cover_after_contain_fallback():
    """정사각(1:1) 스프라이트는 여전히 cover 경로를 타 기존 동작이 안 바뀐다 —
    test_neutral_transform_matches_static_paste와 동일 취지의 회귀 가드."""
    plate = _make_plate()
    sprite = _make_sprite()
    rect = (138, 700, 804, 804)
    radius = 20

    composed = _compose_sibom_into_slot(plate, sprite, rect, radius)

    x, y, w, h = rect
    expected_tile = _paste_rounded(
        plate.convert("RGB").crop((x, y, x + w, y + h)),
        _fit_cover(sprite, w, h),
        0, 0, radius,
    )
    expected = plate.convert("RGB").copy()
    expected.paste(expected_tile, (x, y))

    assert composed.tobytes() == expected.tobytes()

# ── Phase 2 배선 (2026-08-21): 렌더 루프 → 모션 프레임 → 타임라인 ─────────
# 프레임 렌더러를 건드리지 않고 캐릭터 캔버스 안에서 변형하는 방식이 실제로
# entry에 경로를 심고, 타임라인이 그 경로를 소비하는지 계약을 고정한다.

def _sibom_sprite(size=(120, 120)):
    im = Image.new("RGBA", size, (0, 0, 0, 0))
    ImageDraw.Draw(im).ellipse((10, 10, size[0] - 10, size[1] - 10), fill=(255, 248, 240, 255))
    return im


def test_variant_keeps_canvas_size_and_scales_content():
    from ai_worker.renderer.layout import _sibom_variant
    sprite = _sibom_sprite()
    for scale in (0.92, 1.0, 1.03):
        out = _sibom_variant(sprite, scale=scale)
        assert out.size == sprite.size          # 캔버스 유지 = 미디어 박스 안정
    faded = _sibom_variant(sprite, alpha=0.35)
    assert faded.getchannel("A").getextrema()[1] < 255


def test_wire_sibom_motion_populates_entry(tmp_path):
    from ai_worker.renderer.layout import (
        _wire_sibom_motion, _SIBOM_PUNCH_POP_FRAMES, _SIBOM_BREATHE_FRAMES,
    )
    rendered = []

    def render_frame(img, out_path):
        rendered.append(out_path)
        img.convert("RGB").save(str(out_path), "PNG")

    entry = {"sibom_role": "peak", "sibom_image_id": "waiting-reply", "sibom_dwell": "hold"}
    _wire_sibom_motion(entry, render_frame, _sibom_sprite(), tmp_path, 3)

    assert len(entry["sibom_punch_paths"]) == _SIBOM_PUNCH_POP_FRAMES
    assert len(entry["sibom_loop_paths"]) == _SIBOM_BREATHE_FRAMES   # waiting-reply = sway
    assert all(Path(p).exists() for p in entry["sibom_punch_paths"])
    assert len(rendered) == _SIBOM_PUNCH_POP_FRAMES + _SIBOM_BREATHE_FRAMES


def test_wire_skips_punch_dwell_loop_and_non_sibom(tmp_path):
    from ai_worker.renderer.layout import _wire_sibom_motion

    def render_frame(img, out_path):
        img.convert("RGB").save(str(out_path), "PNG")

    punch_entry = {"sibom_role": "punch", "sibom_image_id": "waiting-reply",
                   "sibom_dwell": "punch"}
    _wire_sibom_motion(punch_entry, render_frame, _sibom_sprite(), tmp_path, 1)
    assert punch_entry["sibom_punch_paths"]
    assert "sibom_loop_paths" not in punch_entry     # punch dwell엔 루프 없음

    plain = {"type": "image_text"}
    _wire_sibom_motion(plain, render_frame, _sibom_sprite(), tmp_path, 2)
    assert plain == {"type": "image_text"}           # 시봄이 아니면 무동작


def test_wired_entry_feeds_visual_timeline(tmp_path):
    """배선 결과가 타임라인에 실제로 반영되는지 — Phase 2의 핵심 계약."""
    from ai_worker.renderer.layout import (
        _wire_sibom_motion, _build_visual_timeline, _SIBOM_PUNCH_SEC,
    )

    def render_frame(img, out_path):
        img.convert("RGB").save(str(out_path), "PNG")

    entry = {"type": "image_text", "sibom_role": "peak",
             "sibom_image_id": "two-argue", "sibom_dwell": "hold"}   # shake
    _wire_sibom_motion(entry, render_frame, _sibom_sprite(), tmp_path, 0)

    base = tmp_path / "frame_000.png"
    Image.new("RGB", (40, 40)).save(str(base), "PNG")
    timeline = _build_visual_timeline([base], [entry], [6.0])

    used = {p for p, _ in timeline}
    assert Path(entry["sibom_punch_paths"][0]) in used
    assert Path(entry["sibom_loop_paths"][0]) in used
    assert base not in used                                  # 정지 프레임을 쓰지 않는다
    assert sum(d for _, d in timeline) == pytest.approx(6.0)
    punch_total = sum(d for p, d in timeline
                      if str(p) in entry["sibom_punch_paths"])
    assert punch_total == pytest.approx(_SIBOM_PUNCH_SEC)
