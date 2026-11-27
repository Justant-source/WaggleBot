"""보이스 키 → Supertonic 프리셋(M1~M5, F1~F5) 결정적 해석.

- 이미 프리셋 키(대소문자 무관)면 그대로(대문자 정규화).
- 구 키(Fish 참조 음성 등)는 성별을 보존해 같은 성별 프리셋으로 매핑한다.
  같은 post_id에서 서로 다른 구 키는 (가능한 한) 서로 다른 프리셋이 되도록
  ``random.Random(post_id)``로 섞은 프리셋 순열에서 구 키의 고정 서수로 고른다.
- None/알 수 없는 키는 post_id 시드로 전체 10종에서 고른다. post_id도 없으면 ``F1``.
"""
from __future__ import annotations

import random

MALE_PRESETS: tuple[str, ...] = ("M1", "M2", "M3", "M4", "M5")
FEMALE_PRESETS: tuple[str, ...] = ("F1", "F2", "F3", "F4", "F5")
PRESETS: tuple[str, ...] = MALE_PRESETS + FEMALE_PRESETS

DEFAULT_PRESET = "F1"

# 구 키 → 성별 그룹 내 고정 서수 순서 (앞쪽일수록 서로 겹치지 않는 우선권).
# 출처: config/voices.json v3 및 이전 카탈로그(68c38de), settings.py TTS_VOICES, pipeline.json,
# scene/settings.yaml, 문서. 서수 순서를 바꾸면 기존 글의 매핑이 달라지므로 끝에만 추가한다.
_LEGACY_MALE: tuple[str, ...] = (
    "typecast_ref_v2", "kangil_ref", "typecast_ref", "yohan", "manbo", "manu",
    "host_m", "christian", "deep_lax", "krishna", "miguel", "min_jun", "theo", "yohan_koo",
    "ko-kr-injoonneural", "ko-kr-hyunsuneural", "ko-kr-bongjinneural", "ko-kr-gookminneural",
)
_LEGACY_FEMALE: tuple[str, ...] = (
    "seohyeon_ref", "kyunghwa_ref", "yura", "host_f", "hyoeun_ref", "anna", "krys", "sunny",
    "anna_kim", "blondie", "callie", "han", "hope", "ivanna", "lucy", "norah", "tara",
    "ko-kr-sunhineural",
)

LEGACY_GENDER: dict[str, str] = {
    **{k: "male" for k in _LEGACY_MALE},
    **{k: "female" for k in _LEGACY_FEMALE},
}


def _ordinal(key: str, gender: str) -> int:
    group = _LEGACY_MALE if gender == "male" else _LEGACY_FEMALE
    return group.index(key)


def resolve_voice(voice_key: str | None, post_id: int | None = None) -> str:
    """voice_key를 항상 ``M1..F5`` 중 하나로 해석한다(결정적)."""
    key = (voice_key or "").strip()
    norm = key.lower()

    if norm.upper() in PRESETS:
        return norm.upper()

    gender = LEGACY_GENDER.get(norm)
    if gender:
        pool = list(MALE_PRESETS if gender == "male" else FEMALE_PRESETS)
        random.Random(post_id if post_id is not None else 0).shuffle(pool)
        return pool[_ordinal(norm, gender) % len(pool)]

    if post_id is None:
        return DEFAULT_PRESET
    return random.Random(post_id).choice(PRESETS)
