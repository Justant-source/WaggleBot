"""voice_resolver 단위 테스트: 결정성·성별 보존·구 키 전수 커버."""
import pytest

from ai_worker.tts.voice_resolver import (
    FEMALE_PRESETS, LEGACY_GENDER, MALE_PRESETS, PRESETS, resolve_voice,
)


def test_presets_shape():
    assert PRESETS == ("M1", "M2", "M3", "M4", "M5", "F1", "F2", "F3", "F4", "F5")


@pytest.mark.parametrize("key", ["M1", "m3", "f5", " F2 "])
def test_preset_passthrough_case_insensitive(key):
    assert resolve_voice(key, post_id=99) == key.strip().upper()


@pytest.mark.parametrize("key", sorted(LEGACY_GENDER))
@pytest.mark.parametrize("post_id", [None, 0, 1, 12345])
def test_legacy_gender_preserved_and_deterministic(key, post_id):
    out = resolve_voice(key, post_id)
    pool = MALE_PRESETS if LEGACY_GENDER[key] == "male" else FEMALE_PRESETS
    assert out in pool
    assert out == resolve_voice(key.upper(), post_id)


def test_core_legacy_keys_covered():
    for k in ["seohyeon_ref", "typecast_ref_v2", "kangil_ref", "kyunghwa_ref", "yura", "yohan",
              "manbo", "manu", "host_m", "host_f", "typecast_ref", "hyoeun_ref"]:
        assert k in LEGACY_GENDER


def test_distinct_legacy_keys_same_post_get_distinct_presets():
    for pid in range(50):
        m = {resolve_voice(k, pid) for k in ("typecast_ref_v2", "kangil_ref")}
        f = {resolve_voice(k, pid) for k in ("seohyeon_ref", "kyunghwa_ref")}
        assert len(m) == 2 and len(f) == 2


def test_post_id_varies_mapping():
    assert len({resolve_voice("seohyeon_ref", pid) for pid in range(100)}) > 1


@pytest.mark.parametrize("key", [None, "", "unknown_voice"])
def test_unknown_or_none(key):
    assert resolve_voice(key) == "F1"
    assert resolve_voice(key, 7) == resolve_voice(key, 7)
    assert resolve_voice(key, 7) in PRESETS
    assert len({resolve_voice(key, p) for p in range(200)}) == 10
