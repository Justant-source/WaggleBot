"""성별·연령 기반 voice_key 선택 유틸리티.

voices.json의 gender/age_range 메타데이터를 기반으로
사연자 및 등장인물에게 가장 유사한 음성을 배정한다.
"""
from __future__ import annotations

import logging

from config.settings import VOICE_DEFAULT, VOICE_PRESETS

logger = logging.getLogger(__name__)

# age 문자열 → 중간값 (나이대 추정용)
_AGE_MID: dict[str, float] = {
    "10s": 15, "20s": 25, "30s": 35, "40s": 45, "50s": 55, "60s": 65,
}


def pick_voice(
    gender: str = "",
    age: str = "",
    exclude: set[str] | None = None,
) -> str:
    """gender('male'|'female') + age('20s'~'60s') 기반으로 최적 voice_key를 반환한다.

    우선순위: 성별 일치 → 연령 근접. 성별 일치 후보가 없으면 전체에서 연령 근접 선택.
    모든 후보가 exclude에 있으면 VOICE_DEFAULT로 폴백.
    """
    exclude = exclude or set()
    target = _AGE_MID.get(age, 0.0)

    # gender/age_range 메타데이터가 있는 후보만
    pool = [(k, v) for k, v in VOICE_PRESETS.items() if k not in exclude and v.get("age_range")]

    if not pool:
        return VOICE_DEFAULT

    def _dist(v: dict, penalise_gender: bool) -> float:
        mid = sum(v["age_range"]) / 2
        age_d = abs(mid - target) if target else 0.0
        gender_d = 0.0 if (not gender or v.get("gender") == gender) else (50.0 if penalise_gender else 0.0)
        return gender_d + age_d

    # 1차: 성별 페널티 적용
    best_key = min(pool, key=lambda kv: _dist(kv[1], penalise_gender=True))[0]
    # 성별 불일치 페널티(50)가 최소값보다 크면 후보가 없다는 뜻이 아니라 가장 가까운 것 선택
    return best_key
