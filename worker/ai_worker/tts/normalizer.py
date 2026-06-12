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
    native_number,
    read_digits,
    sino_number,
)

logger = logging.getLogger(__name__)

# ㅋㅋ/ㅎㅎ → (laughing) 마커 변환 게이트 (기본 off). settings에서 로드, 실패 시 False.
try:
    from config.settings import TTS_LAUGH_MARKER_ENABLED as _LAUGH_MARKER_DEFAULT
except Exception:  # settings 부분 로드/순환참조 방어
    _LAUGH_MARKER_DEFAULT = False

# 도량형/데이터 단위 → 한국어 (숫자 뒤에서만 변환). 정의 순서 = 매칭 우선순위(긴 단위 먼저).
# 주의: g(그램)/l(리터) 단독 소문자는 "5G"(통신세대) 등과 충돌하므로 제외.
_METRIC_UNITS: list[tuple[str, str]] = [
    ("GB", "기가바이트"), ("MB", "메가바이트"), ("TB", "테라바이트"), ("KB", "킬로바이트"),
    ("km", "킬로미터"), ("kg", "킬로그램"), ("cm", "센티미터"),
    ("mm", "밀리미터"), ("ml", "밀리리터"), ("m", "미터"),
]

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

# 내장 축약어 사전 (항상 적용; assets/slang_map.json이 있으면 그 위에 병합)
# ⚠ assets/는 .gitignore 대상이라 핵심 약어는 반드시 여기(코드)에 둔다.
_SLANG_MAP_BUILTIN: dict[str, str] = {
    # 한글 인터넷 축약어
    "남친": "남자친구", "여친": "여자친구",
    "베댓": "베스트 댓글",
    "갑분싸": "갑자기 분위기 싸해짐",
    "시모": "시어머니", "장모": "장모님",
    "솔까말": "솔직히 까놓고 말해서",
    "킹받": "화가 남", "억까": "억지로 까는",
    "ㄹㅇ": "진짜", "ㅇㅇ": "응", "ㄴㄴ": "아니",
    "ㅇㅋ": "오케이", "ㄱㅅ": "감사", "ㅈㅅ": "죄송",
    "ㅂㅂ": "바이바이", "ㄷㄷ": "",
    "N잡": "엔잡", "U턴": "유턴",
    # 영문 약어 → 한글 발음 (ASCII 키 → 조사교정 후 단어경계 치환)
    "TMI": "티엠아이", "MBTI": "엠비티아이",
    "CCTV": "씨씨티비", "SNS": "에스엔에스", "USB": "유에스비",
    "OTT": "오티티", "GPS": "지피에스", "ATM": "에이티엠", "CEO": "씨이오",
    "AS": "에이에스", "DM": "디엠", "PC": "피씨", "TV": "티비",
    "AI": "에이아이", "IT": "아이티", "PT": "피티", "MT": "엠티",
    "QR": "큐알", "VIP": "브이아이피", "FAQ": "에프에이큐", "PPT": "피피티",
    "API": "에이피아이", "URL": "유알엘", "ID": "아이디", "OS": "오에스",
    "5G": "오지", "LTE": "엘티이",
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
    """축약어 사전 로드 = 내장 사전 + (선택) assets/slang_map.json 오버라이드.

    핵심 약어는 _SLANG_MAP_BUILTIN(코드)에 있어 항상 적용된다. assets/는 .gitignore
    대상이므로 JSON은 배포본에 없을 수 있다 — 있으면 내장값 위에 update로 병합
    (교체 금지: ㄹㅇ·남친 등 내장 항목 소실 방지). 사용자가 도메인 약어를 추가할 때 사용.
    """
    base = dict(_SLANG_MAP_BUILTIN)
    if SLANG_MAP_PATH.exists():
        try:
            loaded: dict[str, str] = json.loads(SLANG_MAP_PATH.read_text(encoding="utf-8"))
            base.update(loaded)
            logger.debug("slang_map.json 병합: +%d 항목", len(loaded))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("slang_map.json 로드 실패, 내장 사전만 사용: %s", exc)
    return base


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

# 슬랭 사전을 두 그룹으로 분할 (긴 키 우선 정렬):
#  - KO: 한글/자모 키(남친·ㄹㅇ 등) → substring 치환 후 조사 교정 적용
#  - EN: 영문 약어 키(AI·CCTV 등) → 조사 교정 *이후* 단어경계 lookaround 치환
#    조사 교정 이후에 둬야 'AI'→'에이아이'의 끝 '이'가 주격조사로 오인돼
#    '에이아가'로 망가지는 것을 막는다. lookaround는 '5GB' 내부 'AI' 등 오매칭 방지.
_SLANG_KO_SORTED: list[tuple[str, str]] = sorted(
    ((k, v) for k, v in _SLANG_MAP.items() if not k.isascii()),
    key=lambda x: -len(x[0]),
)
_SLANG_EN_SORTED: list[tuple[str, str]] = sorted(
    ((k, v) for k, v in _SLANG_MAP.items() if k.isascii()),
    key=lambda x: -len(x[0]),
)


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


# 조사 쌍 (받침 있음, 받침 없음) + 매칭용 정규식 (긴 조사 우선)
_PARTICLE_PAIRS: list[tuple[str, str]] = [
    ("과", "와"), ("은", "는"), ("이", "가"), ("을", "를"), ("아", "야"),
]
_PARTICLE_ALT = "으로|로|과|와|은|는|이|가|을|를|아|야"


def _fix_trailing_particle(prev_char: str, particle: str) -> str:
    """slang 치환 결과의 마지막 글자 받침에 맞춰 바로 뒤 조사를 교정한다."""
    if particle in ("으로", "로"):
        # ㄹ받침/무받침 → "로", 그 외 → "으로"
        if has_rieul_jongseong(prev_char) or not has_jongseong(prev_char):
            return "로"
        return "으로"
    for with_jong, without_jong in _PARTICLE_PAIRS:
        if particle in (with_jong, without_jong):
            return with_jong if has_jongseong(prev_char) else without_jong
    return particle


def apply_ko_slang(text: str) -> str:
    """한글 축약어를 치환하고, 치환된 단어 바로 뒤의 조사만 교정한다.

    조사 교정을 슬랭 경계로 한정한다. 과거 전역 fix_particles는 '마을'→'마를',
    '사과'→'사와'처럼 일반 단어의 끝 음절을 조사로 오인해 망가뜨렸다.
    예: '남친과' → '남자친구와', '베댓을' → '베스트 댓글을'.
    """
    for slang, replacement in _SLANG_KO_SORTED:
        if slang not in text:
            continue
        pattern = re.compile(
            re.escape(slang) + rf'(?:({_PARTICLE_ALT})(?=\s|$|[^가-힣]))?'
        )

        def _rep(m, repl=replacement) -> str:
            particle = m.group(1)
            if not particle or not repl:
                return repl
            return repl + _fix_trailing_particle(repl[-1], particle)

        text = pattern.sub(_rep, text)
    return text


def _convert_range(match: re.Match) -> str:  # type: ignore[type-arg]
    """범위 표현 'A~B(단위)' → 'A에서 B (단위)'. 단위에 따라 sino/native 선택."""
    a, b = int(match.group(1)), int(match.group(2))
    counter = match.group(3)
    reader = native_number if (counter and counter in NATIVE_COUNTERS) else sino_number
    body = f"{reader(a)}에서 {reader(b)}"
    return f"{body} {counter}" if counter else body


def _read_num(s: str) -> str:
    """정수/소수 문자열을 한국어 읽기로. '3'→'삼', '3.5'→'삼 점 오'."""
    if "." in s:
        int_part, frac = s.split(".", 1)
        return f"{sino_number(int(int_part))} 점 {read_digits(frac)}"
    return sino_number(int(s))


def _convert_phone(match: re.Match) -> str:  # type: ignore[type-arg]
    """하이픈 전화번호 '010-1234-5678' → 자릿수 읽기 (구간별 공백)."""
    return " ".join(read_digits(g) for g in match.groups() if g)


def _convert_numbers(text: str) -> str:
    """숫자 표현을 한국어 읽기로 변환한다 (순서 의존적 — 호출 순서 변경 금지)."""
    # 1. 천단위 콤마 제거: 1,200,000 → 1200000
    text = re.sub(r'(?<!\d)(\d{1,3}(?:,\d{3})+)(?!\d)', lambda m: m.group(1).replace(",", ""), text)
    # 2. 전화번호 → 자릿수 읽기 (큰 숫자 변환보다 먼저)
    text = re.sub(r'(?<!\d)(\d{2,4})-(\d{3,4})-(\d{4})(?!\d)', _convert_phone, text)
    text = re.sub(r'(?<!\d)(01[016789])(\d{3,4})(\d{4})(?!\d)', _convert_phone, text)
    # 3. 월 불규칙 발음: 6월→유월, 10월→시월 (일반 단위 변환보다 먼저)
    text = re.sub(r'(?<!\d)6\s*월', '유월', text)
    text = re.sub(r'(?<!\d)10\s*월', '시월', text)
    # 4. 범위 A~B(단위) — 물결표 제거(step 4)보다 먼저
    counters_for_range = "|".join(
        re.escape(c) for c in sorted(NATIVE_COUNTERS | SINO_COUNTERS, key=len, reverse=True)
    )
    text = re.sub(
        rf'(?<!\d)(\d+)\s*[~∼〜～]\s*(\d+)\s*({counters_for_range})?',
        _convert_range, text,
    )
    # 5. 퍼센트 (소수 포함) — 소수 단독 변환보다 먼저
    text = re.sub(r'(?<!\d)(\d+(?:\.\d+)?)\s*%', lambda m: _read_num(m.group(1)) + " 퍼센트", text)
    # 6. 도량형 단위 (km/kg/cm/mm/ml/m, 소수 포함) — 소수/단위 단독 변환보다 먼저
    metric_alt = "|".join(u for u, _ in _METRIC_UNITS)  # 긴 단위 우선 (정의 순서)
    _metric_map = dict(_METRIC_UNITS)
    text = re.sub(
        rf'(?<!\d)(\d+(?:\.\d+)?)\s*({metric_alt})(?![A-Za-z가-힣])',
        lambda m: f"{_read_num(m.group(1))} {_metric_map[m.group(2)]}", text,
    )
    # 7. 소수 단독 (정수부 sino + 소수부 자릿수) — 단독 숫자 변환보다 먼저
    text = re.sub(r'(?<!\d)(\d+)\.(\d+)(?!\d)', lambda m: _read_num(m.group(0)), text)
    # 8. 숫자+단위 (기존)
    all_counters = "|".join(
        re.escape(c) for c in sorted(NATIVE_COUNTERS | SINO_COUNTERS, key=len, reverse=True)
    )
    text = re.sub(rf'(\d+)\s*({all_counters})', convert_number_with_counter, text)
    # 9. 단독 숫자 (기존)
    text = re.sub(r'\d+', convert_standalone_number, text)
    return text


def normalize_for_tts(text: str, *, laugh_marker: bool | None = None) -> str:
    """TTS 전달 전 한국어 인터넷 슬랭/이모티콘 정규화.

    Fish Speech 토크나이저가 처리하지 못하는 비표준 문자를 제거해
    중국어 폴백 발음과 어색한 합성을 방지한다.

    Args:
        text:         원문
        laugh_marker: ㅋㅋ/ㅎㅎ → (laughing) 마커 변환 여부.
                      None이면 settings.TTS_LAUGH_MARKER_ENABLED 사용.
    """
    if laugh_marker is None:
        laugh_marker = _LAUGH_MARKER_DEFAULT

    # 0. 화자 접두어 제거: "ㅇㅇ: ", "댓글: " 등
    text = re.sub(r'^[가-힣A-Za-z0-9]{1,8}:\s*', '', text)

    # 1. 한글 축약어 치환 + 치환 경계의 조사 교정 (남친과 → 남자친구와)
    text = apply_ko_slang(text)

    # 1-1a. 영문 약어 치환 (단어경계 lookaround) — 조사 교정 *이후* 적용
    for acronym, replacement in _SLANG_EN_SORTED:
        text = re.sub(
            rf'(?<![A-Za-z0-9]){re.escape(acronym)}(?![A-Za-z0-9])',
            replacement, text,
        )

    # 1-1b. 웃음 마커 — soynlp 축약/자모 삭제 전에 (laughing) 으로 치환 (게이트)
    #   순서 중요: soynlp가 ㅋㅋㅋ→ㅋ로 줄이고 step 2가 단독 자모를 삭제하므로
    #   그 전에 변환해야 한다. ASCII 괄호는 step 4 따옴표 제거에 영향받지 않음.
    if laugh_marker:
        text = re.sub(r'[ㅋ]{2,}|[ㅎ]{2,}', ' (laughing) ', text)

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

    # 3. URL/이메일/해시태그 제거 (숫자 변환 전 — URL 내 숫자 오변환 방지)
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r'[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}', '', text)
    text = re.sub(r'#\S+', '', text)

    # 3-1. 숫자 → 한국어 읽기 변환 (콤마/전화/월/범위/소수/단위/단독)
    text = _convert_numbers(text)

    # 3-2. 발음 교정 사전 — 비활성화 (2026-03-08)
    # Fish Speech는 자체 G2P로 한국어 발음 규칙(경음화·비음화·ㅎ탈락 등)을 처리.
    # phonetic 변환은 모델 학습 데이터에 없는 비표준 표기로 중국어 회귀·발음 왜곡 유발.

    # 4. 특수문자 정리
    text = text.replace("。", ".").replace("、", ",")   # 중국어/일본어 구두점
    text = text.replace("~", " ").replace("～", " ")    # 잔여 물결표 → 공백
    text = re.sub(r"['\"""''「」『』【】`]", " ", text)   # 따옴표/인용부호 → 공백
    text = re.sub(r'\.{3,}', '…', text)                 # 말줄임표 통일
    text = re.sub(r'\s+', ' ', text)                    # 연속 공백 정리

    # 5. 문장 완성 — 마침표 없는 끝에 마침표 추가 (프로소디 안정화)
    #    마커로 끝나는 경우((laughing) 등)는 마침표 불필요
    text = text.strip()
    if text and text[-1] not in '.!?…)':
        text += '.'

    return text
