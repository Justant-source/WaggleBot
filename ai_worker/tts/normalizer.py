"""ai_worker/tts/normalizer.py — 한국어 텍스트 정규화 (TTS 전처리)"""

import json
import logging
import re
from pathlib import Path

from ai_worker.tts.number_reader import (
    NATIVE_COUNTERS,
    SINO_COUNTERS,
    convert_number_with_counter,
    convert_standalone_number,
    sino_number,
)

logger = logging.getLogger(__name__)

# ── 선택적 라이브러리 (미설치 시 내장 구현으로 폴백) ──
try:
    from soynlp.normalizer import repeat_normalize as _soynlp_repeat_normalize
    _SOYNLP_AVAILABLE = True
    logger.debug("soynlp 로드 완료")
except ImportError:
    _SOYNLP_AVAILABLE = False

# ── 사전 경로 ──
SLANG_MAP_PATH = Path(__file__).parent.parent.parent / "assets" / "slang_map.json"
PRONUNCIATION_MAP_PATH = Path(__file__).parent.parent.parent / "assets" / "pronunciation_map.json"

# 내장 축약어 사전 (slang_map.json 없을 때 폴백)
_SLANG_MAP_BUILTIN: dict[str, str] = {
    "남친": "남자친구", "여친": "여자친구",
    "베댓": "베스트 댓글",
    "갑분싸": "갑자기 분위기 싸해짐",
    "시모": "시어머니", "장모": "장모님",
    "솔까말": "솔직히 까놓고 말해서",
    "킹받": "화가 남", "억까": "억지로 까는",
    "ㄹㅇ": "진짜", "ㅇㅇ": "응", "ㄴㄴ": "아니",
    "ㅇㅋ": "오케이", "ㄱㅅ": "감사", "ㅈㅅ": "죄송",
    "ㅂㅂ": "바이바이", "ㄷㄷ": "",
    "TMI": "티엠아이", "MBTI": "엠비티아이",
}

# 내장 발음 교정 사전: 맞춤법 표기 → 실제 발음형
_PRONUNCIATION_MAP_BUILTIN: dict[str, str] = {
    # 경음화 (받침 ㄷ/ㅂ/ㄱ + ㄱ/ㄷ/ㅂ/ㅅ/ㅈ → 경음)
    "댓글": "대끌",
    "맛집": "마찝",
    "꽃길": "꼳낄",
    "숫자": "숟짜",
    "곳곳": "곧꼳",
    "낱개": "나깨",
    "갯벌": "개뻘",
    "웃기": "욷끼",
    "있다": "읻따",
    "없다": "업따",
    "있고": "읻꼬",
    "없고": "업꼬",
    "있는": "인는",
    "없는": "엄는",
    "있습니다": "읻씀니다",
    "없습니다": "업씀니다",
    "있었": "이썯",
    "없었": "업썯",
    "했습니다": "해씀니다",
    "됐습니다": "돼씀니다",
    # 비음화 (받침 ㄱ/ㄷ/ㅂ + ㄴ/ㅁ → 비음)
    "작년": "장년",
    "국내": "궁내",
    "국민": "궁민",
    "학년": "항년",
    "합니다": "함니다",
    "십만": "심만",
    "백만": "뱅만",
    # 유음화 (ㄴ+ㄹ, ㄹ+ㄴ → ㄹㄹ)
    "관련": "괄련",
    "연락": "열락",
    # 구개음화
    "같이": "가치",
    "굳이": "구지",
    "붙이": "부치",
    # ㅎ 약화/탈락
    "좋아": "조아",
    "좋은": "조은",
    "좋다": "조타",
    "놓다": "노타",
    "넣다": "너타",
    "않다": "안타",
    "않은": "아는",
    "않아": "아나",
    "많다": "만타",
    "많은": "마는",
    "많이": "마니",
    "괜찮": "괜찬",
    # 겹받침
    "읽다": "익따",
    "읽고": "익꼬",
    "읽는": "잉는",
    "없는": "엄는",
    "삶": "삼",
    "젊은": "절문",
    "밟다": "밥따",
    # 연음
    "높이": "노피",
    # 자주 틀리는 일상어
    "뭐라고": "뭐라고",
    "남겨주세요": "남겨주세요",
}


def load_slang_map() -> dict[str, str]:
    """assets/slang_map.json에서 축약어 사전 로드. 파일 없으면 내장 사전 사용."""
    if SLANG_MAP_PATH.exists():
        try:
            loaded: dict[str, str] = json.loads(SLANG_MAP_PATH.read_text(encoding="utf-8"))
            logger.debug("slang_map.json 로드: %d 항목", len(loaded))
            return loaded
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("slang_map.json 로드 실패, 내장 사전 사용: %s", exc)
    return dict(_SLANG_MAP_BUILTIN)


def load_pronunciation_map() -> dict[str, str]:
    """assets/pronunciation_map.json에서 발음 사전 로드. 파일 없으면 내장 사전 사용."""
    base = dict(_PRONUNCIATION_MAP_BUILTIN)
    if PRONUNCIATION_MAP_PATH.exists():
        try:
            loaded: dict[str, str] = json.loads(
                PRONUNCIATION_MAP_PATH.read_text(encoding="utf-8")
            )
            base.update(loaded)
            logger.debug("pronunciation_map.json 로드: %d 항목", len(loaded))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("pronunciation_map.json 로드 실패, 내장 사전만 사용: %s", exc)
    return base


# 모듈 레벨 사전 로드
_SLANG_MAP: dict[str, str] = load_slang_map()
_PRONUNCIATION_MAP: dict[str, str] = load_pronunciation_map()


# ── 겹받침 단순화 테이블 (표준 발음법 제10항) ──
# 자음 앞·어말에서 겹받침 → 대표 단자음
_DOUBLE_JONG_SIMPLIFY: dict[int, int] = {
    3:  1,   # ㄳ → ㄱ
    5:  4,   # ㄵ → ㄴ
    6:  4,   # ㄶ → ㄴ
    9:  1,   # ㄺ → ㄱ
    10: 16,  # ㄻ → ㅁ
    11: 8,   # ㄼ → ㄹ
    12: 8,   # ㄽ → ㄹ
    13: 8,   # ㄾ → ㄹ
    14: 17,  # ㄿ → ㅂ
    15: 8,   # ㅀ → ㄹ
    18: 17,  # ㅄ → ㅂ
}

# ── 비음화 테이블 (표준 발음법 제18항) ──
# 폐쇄음 종성 + ㄴ/ㅁ 초성 → 비음 종성
_NASALIZATION_MAP: dict[int, int] = {
    17: 16,  # ㅂ → ㅁ
    26: 16,  # ㅍ → ㅁ
    1:  21,  # ㄱ → ㅇ
    2:  21,  # ㄲ → ㅇ
    24: 21,  # ㅋ → ㅇ
    7:  4,   # ㄷ → ㄴ
    19: 4,   # ㅅ → ㄴ
    20: 4,   # ㅆ → ㄴ
    22: 4,   # ㅈ → ㄴ
    23: 4,   # ㅊ → ㄴ
    25: 4,   # ㅌ → ㄴ
}
_NASAL_CHOSEONG: frozenset[int] = frozenset({2, 6})  # 초성 ㄴ(2), ㅁ(6)


def has_jongseong(char: str) -> bool:
    """받침 유무 확인 (유니코드 연산)."""
    if not char or not ('가' <= char <= '힣'):
        return False
    return (ord(char) - 0xAC00) % 28 != 0


def has_rieul_jongseong(char: str) -> bool:
    """ㄹ 받침 여부 확인."""
    if not char or not ('가' <= char <= '힣'):
        return False
    return (ord(char) - 0xAC00) % 28 == 8  # ㄹ = jongseong index 8


# 조사 교정 제외 종성: 겹받침 + ㅆ (용언 어간에 주로 출현)
# 이들 뒤 은/는/이/가 등은 조사가 아닌 어미일 가능성이 높음
_VERB_STEM_JONGSEONG: frozenset[int] = frozenset(_DOUBLE_JONG_SIMPLIFY.keys()) | {20}  # ㅆ


def _has_verb_stem_jongseong(char: str) -> bool:
    """용언 어간에 주로 나타나는 종성(겹받침·ㅆ) 여부 확인."""
    if not char or not ('가' <= char <= '힣'):
        return False
    return (ord(char) - 0xAC00) % 28 in _VERB_STEM_JONGSEONG


def fix_particles(text: str) -> str:
    """받침 유무에 따른 조사 자동 교정.

    축약어 치환 후 받침이 달라져 조사가 맞지 않는 경우 교정.
    예: '남친과' → (축약어 치환) → '남자친구과' → (교정) → '남자친구와'

    겹받침(ㅄ, ㄺ 등) 뒤는 용언 어간일 가능성이 높으므로 교정 건너뜀.
    예: '없는'의 '는'은 관형사형 어미이므로 '은'으로 바꾸면 안 됨.
    """
    particle_pairs = [
        ("과", "와"),
        ("은", "는"),
        ("이", "가"),
        ("을", "를"),
        ("으로", "로"),
        ("아", "야"),
    ]
    for with_jong, without_jong in particle_pairs:
        pattern = re.compile(
            r'([가-힣])('
            + re.escape(with_jong) + '|' + re.escape(without_jong)
            + r')(?=\s|$|[^가-힣])'
        )
        if with_jong == "으로":
            def _replace(m, wj=with_jong, woj=without_jong) -> str:
                prev = m.group(1)
                if _has_verb_stem_jongseong(prev):
                    return m.group(0)
                if has_rieul_jongseong(prev) or not has_jongseong(prev):
                    return prev + woj  # 로
                return prev + wj       # 으로
        else:
            def _replace(m, wj=with_jong, woj=without_jong) -> str:
                prev = m.group(1)
                if _has_verb_stem_jongseong(prev):
                    return m.group(0)
                return prev + (wj if has_jongseong(prev) else woj)
        text = pattern.sub(_replace, text)
    return text


def simplify_double_jongseong(text: str) -> str:
    """겹받침을 비음 초성 앞·어말에서 단순화 + 비음화 (표준 발음법 제10·18항).

    Fish Speech G2P가 겹받침(ㅄ, ㄺ 등)을 잘못 분리하는 문제를 보수적으로 보완.

    적용 조건:
      - 다음 초성이 ㄴ/ㅁ → 겹받침 단순화 + 비음화 (없는→엄는, 읽는→잉는)
      - 어말 또는 비한글 뒤 → 겹받침 단순화 (삶→삼, 값→갑)
    미적용 조건:
      - 다음 초성이 모음(ㅇ) → 연음 환경, Fish Speech에 위임 (없어→없어)
      - 다음 초성이 기타 자음 → 비표준 텍스트가 중국어 회귀 유발 가능, 유지 (없다→없다)
    """
    chars = list(text)
    result: list[str] = []
    for i, ch in enumerate(chars):
        code = ord(ch) - 0xAC00
        if code < 0 or code > 11171:
            result.append(ch)
            continue
        jong = code % 28
        if jong not in _DOUBLE_JONG_SIMPLIFY:
            result.append(ch)
            continue

        cho = code // (21 * 28)
        jung = (code % (21 * 28)) // 28
        new_jong = _DOUBLE_JONG_SIMPLIFY[jong]

        # 다음 글자가 한글 음절인 경우
        if i + 1 < len(chars):
            next_code = ord(chars[i + 1]) - 0xAC00
            if 0 <= next_code <= 11171:
                next_cho = next_code // (21 * 28)
                # ㅇ 초성(모음) → 연음 환경 → 유지
                if next_cho == 11:
                    result.append(ch)
                    continue
                # ㄴ/ㅁ 초성 → 겹받침 단순화 + 비음화
                if next_cho in _NASAL_CHOSEONG and new_jong in _NASALIZATION_MAP:
                    new_jong = _NASALIZATION_MAP[new_jong]
                    result.append(chr(0xAC00 + cho * 21 * 28 + jung * 28 + new_jong))
                    continue
                # 기타 자음 초성 → 유지 (비표준 텍스트 방지)
                result.append(ch)
                continue

        # 어말 또는 비한글 문자 앞: 겹받침 → 대표 단자음
        result.append(chr(0xAC00 + cho * 21 * 28 + jung * 28 + new_jong))
    return "".join(result)


def normalize_for_tts(text: str) -> str:
    """TTS 전달 전 한국어 인터넷 슬랭/이모티콘 정규화.

    Fish Speech 토크나이저가 처리하지 못하는 비표준 문자를 제거해
    중국어 폴백 발음과 어색한 합성을 방지한다.
    """
    # 0. 화자 접두어 제거: "ㅇㅇ: ", "댓글: " 등
    text = re.sub(r'^[가-힣A-Za-z0-9]{1,8}:\s*', '', text)

    # 1. 인터넷 축약어 치환 (긴 키워드 우선)
    for slang, replacement in sorted(_SLANG_MAP.items(), key=lambda x: -len(x[0])):
        text = text.replace(slang, replacement)

    # 1-1. 조사 자동 교정 (축약어 치환 후 받침 변경 대응)
    text = fix_particles(text)

    # 1-2. soynlp: 반복 자모 정규화 — 삭제 전 반복 횟수 통일 (ㅋㅋㅋㅋ → ㅋ)
    if _SOYNLP_AVAILABLE:
        try:
            text = _soynlp_repeat_normalize(text, num_repeats=1)
        except Exception:
            logger.warning("soynlp repeat_normalize 실패, 건너뜀")

    # 2. 자모 이모티콘 제거
    text = re.sub(r'[ㅋㅎㅠㅜㅡ]{2,}', '', text)  # 2회 이상 반복 자모 삭제
    text = re.sub(r'[ㄱ-ㅎㅏ-ㅣ]+', '', text)       # 나머지 단독 자모 삭제
    text = re.sub(r'\^+', '', text)                  # ^ 이모티콘 제거

    # 3. 숫자 → 한국어 읽기 변환 (built-in만 사용)
    all_counters = "|".join(
        re.escape(c) for c in sorted(NATIVE_COUNTERS | SINO_COUNTERS, key=len, reverse=True)
    )
    text = re.sub(rf'(\d+)\s*({all_counters})', convert_number_with_counter, text)
    text = re.sub(r'(\d+)\s*%', lambda m: sino_number(int(m.group(1))) + " 퍼센트", text)
    text = re.sub(r'\d+', convert_standalone_number, text)

    # 3-1. 겹받침 단순화 + 후속 비음화 (Fish Speech G2P 보완)
    # Fish Speech가 겹받침(ㅄ, ㄺ 등)을 잘못 분리하는 문제를 규칙 기반으로 보완.
    # 비음화는 겹받침에서 생긴 종성에만 적용 (전역 비음화는 중국어 회귀 유발).
    text = simplify_double_jongseong(text)

    # 4. 특수문자 정리
    text = text.replace("。", ".").replace("、", ",")   # 중국어/일본어 구두점
    text = text.replace("~", " ").replace("～", " ")    # 물결표 → 공백
    text = re.sub(r"['\"""''「」『』【】`]", " ", text)   # 따옴표/인용부호 → 공백
    text = re.sub(r'\.{3,}', '…', text)                 # 말줄임표 통일
    text = re.sub(r'\s+', ' ', text)                    # 연속 공백 정리

    # 5. 문장 완성 — 마침표 없는 끝에 마침표 추가 (프로소디 안정화)
    text = text.strip()
    if text and text[-1] not in '.!?…':
        text += '.'

    return text
