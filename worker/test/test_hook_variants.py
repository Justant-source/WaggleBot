"""훅 구간 실험 프로필(marketing_hook_a/b/c) 단위 테스트 — ffmpeg 불필요(타임라인 PNG까지만)."""
import copy
from pathlib import Path

import pytest
from PIL import Image

from ai_worker.renderer import hook_variants as hv
from ai_worker.renderer.layout import _load_layout, _deep_merge

FONT_DIR = Path(__file__).resolve().parents[2] / "assets" / "fonts"
pytestmark = pytest.mark.skipif(not (FONT_DIR / "NotoSerifKR-Medium.ttf").exists(), reason="fonts missing")


@pytest.fixture(scope="module")
def layout():
    # 호스트에서 worker/config 는 컨테이너 bind 마운트 지점(빈 디렉토리)이다 — 저장소 루트 config/ 로 대체
    from ai_worker.renderer import layout as layout_mod
    repo_cfg = Path(__file__).resolve().parents[2] / "config" / "layout.json"
    if layout_mod._LAYOUT_CONFIG is None and not (Path(layout_mod.__file__).resolve().parents[2] / "config" / "layout.json").exists():
        if not repo_cfg.exists():
            pytest.skip("layout.json not found")
        import json
        layout_mod._LAYOUT_CONFIG = json.loads(repo_cfg.read_text(encoding="utf-8"))
    lo = copy.deepcopy(_load_layout())
    tone_l = lo.get("themes", {}).get("tone_l", {})
    _deep_merge(lo.setdefault("global", {}), tone_l.get("global", {}))
    _deep_merge(lo.setdefault("scenes", {}), tone_l.get("scenes", {}))
    lo["global"]["theme"] = "tone_l"
    return lo


@pytest.fixture()
def sprite():
    return Image.new("RGBA", (820, 820), (255, 247, 238, 255))


def test_profile_helpers():
    for p in hv.HOOK_PROFILES:
        assert hv.is_hook_profile(p)
        assert hv.base_profile(p) == "marketing_v2"
    assert hv.base_profile("marketing_v2") == "marketing_v2"
    assert hv.base_profile("marketing_fast") == "marketing_fast"
    assert hv.base_profile(None) is None


def test_resolve_render_profile_accepts_hook_profiles(monkeypatch):
    from ai_worker.core import processor
    for p in ("marketing_fast", "marketing_v2", *hv.HOOK_PROFILES):
        monkeypatch.setattr(processor, "_resolve_post_variant_config", lambda pid, p=p: {"render_profile": p})
        assert processor.resolve_render_profile(1) == p
    monkeypatch.setattr(processor, "_resolve_post_variant_config", lambda pid: {"render_profile": "bogus"})
    assert processor.resolve_render_profile(1) == "marketing_fast"


@pytest.mark.parametrize("text,expected", [
    ("남편이 몰래 180만원을 보냈다", True),
    ("3년째 말을 안 했다", True),
    ("밥상에서 처음 본 친척", False),
])
def test_has_number(text, expected):
    assert hv.has_number(text) is expected


def test_split_numbers_keeps_particles_out():
    assert hv._split_numbers("180만원을") == [("180만원", True), ("을", False)]
    assert hv._split_numbers("3년째") == [("3년", True), ("째", False)]


@pytest.mark.parametrize("variant", hv.HOOK_PROFILES)
def test_timeline_total_and_files(variant, layout, sprite, tmp_path):
    total = 5.0
    final, tl = hv.build_hook_timeline(
        variant, sprite, "남편이 몰래 시댁에 180만원을 보냈고 3년째 말을 안 했다",
        layout, FONT_DIR, tmp_path, 0, total,
    )
    assert Path(final).exists()
    assert all(Path(p).exists() and d >= 0 for p, d in tl)
    assert sum(d for _, d in tl) == pytest.approx(total, abs=0.08)


def test_a_without_number_is_single_static_frame(layout, sprite, tmp_path):
    _, tl = hv.build_hook_timeline("marketing_hook_a", sprite, "밥상에서 처음 본 친척", layout, FONT_DIR, tmp_path, 0, 4.0)
    assert len(tl) == 1


def test_c_without_sprite_falls_back_to_static(layout, tmp_path):
    _, tl = hv.build_hook_timeline("marketing_hook_c", None, "밥상에서 처음 본 친척", layout, FONT_DIR, tmp_path, 0, 4.0)
    assert len(tl) == 1


def test_a_hook_font_larger_than_v2(layout):
    fs, *_ = hv._layout_a("밥상에서 처음 본 친척에게 받은 첫 질문이 피임 여부였다", layout, FONT_DIR)
    assert fs >= hv._A_MIN_FS > hv._hook_target_fs()
