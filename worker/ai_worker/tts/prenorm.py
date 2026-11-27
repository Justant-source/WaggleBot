"""ai_worker/tts/prenorm.py — Local-TTS 요청 전 앱 고유 전처리.

숫자·단위·월·범위·소수점·말줄임·따옴표·종결부호는 서버 내장 정규화가, 슬랭·영문 약어는
발음 프로필(``config/tts_profile/shorts-ko.yaml`` → ``wagglebot/shorts-ko``)이 처리한다.
여기에는 프로필로 표현할 수 없는 앱 규칙만 둔다.

- 화자 접두어(``ㅇㅇ: ``) 제거
- URL·이메일·해시태그 삭제 (서버가 숫자로 읽기 전에)
- 자모 슬랭(ㄹㅇ 등)·``ㄷㄷ`` 삭제, 그 외 단독 자모·``^`` 이모티콘 삭제 (ㅋㅋ/ㅎㅎ 웃음은 읽지 않는다)
- ``N대``(범위 ``A~B대`` 포함)·``N기`` 숫자는 한자어 수사로 읽는다(50대→오십 대, 암 4기→사 기). 서버는 ``대``·``기`` 를
  고유어 단위(쉰 대·네 기)로 읽어 연령대·단계·``1대1`` 의미가 틀어진다.

문단 구분(빈 줄)은 서버 청커의 문단 경계이므로 보존한다.
"""

import re

# 자모 슬랭 → 치환어. 프로필 정규화 전에 단독 자모 삭제가 일어나므로 앱에서 먼저 치환한다.
# 빈 문자열은 삭제(프로필 word 는 빈 value 불가).
_JAMO_SLANG: dict[str, str] = {
    "ㄹㅇ": "진짜", "ㅇㅇ": "응", "ㄴㄴ": "아니", "ㅇㅋ": "오케이",
    "ㄱㅅ": "감사", "ㅈㅅ": "죄송", "ㅂㅂ": "바이바이", "ㄷㄷ": "",
}
_JAMO_SLANG_RE = re.compile("|".join(sorted(map(re.escape, _JAMO_SLANG), key=len, reverse=True)))

_SINO_DIGIT = "영일이삼사오육칠팔구"
_SINO_UNIT = ("", "십", "백", "천")
_SINO_BIG = ("", "만", "억", "조")


def _sino(n: int) -> str:
    """정수를 한자어 수사로 읽는다(십·백·천 앞 '일' 생략, 4자리 단위 만/억/조)."""
    if n == 0:
        return "영"
    s = str(n)
    parts: list[str] = []
    for gi, end in enumerate(range(len(s), 0, -4)):
        group = s[max(0, end - 4):end]
        out = ""
        for j, d in enumerate(reversed(group)):
            if d == "0":
                continue
            out = (_SINO_UNIT[j] if d == "1" and j else _SINO_DIGIT[int(d)] + _SINO_UNIT[j]) + out
        if out:
            if out == "일" and gi == 1:      # 10000 → 만 (일만 아님)
                out = ""
            parts.append(out + _SINO_BIG[gi])
    return "".join(reversed(parts))


def _sino_range(m: re.Match) -> str:
    a, b = (int(g.replace(",", "")) for g in m.group(1, 2))
    return f"{_sino(a)}에서 {_sino(b)} 대"


def _force_sino(m: re.Match) -> str:
    digits = m.group(1).replace(",", "")
    return f"{_sino(int(digits))} {m.group(2) or m.group(3)}"


_SPEAKER_RE = re.compile(r"^[가-힣A-Za-z0-9]{1,8}:\s*")
_URL_RE = re.compile(r"https?://\S+")
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}")
_HASHTAG_RE = re.compile(r"#\S+")
_SINO_COUNTER_RE = re.compile(
    r"(?<![\d.])(\d+(?:,\d{3})*)\s*(?:(대)|(기)(?=$|[^가-힣]|[은는이을를와과의도에로]))"
)
_SINO_RANGE_RE = re.compile(r"(?<![\d.])(\d+)\s*[~∼〜～]\s*(\d+)\s*대")
_JAMO_RE = re.compile(r"[ㄱ-ㅎㅏ-ㅣ]+")


def prenormalize(text: str) -> str:
    """Local-TTS 로 보낼 텍스트의 앱 전처리. 빈 입력은 빈 문자열."""
    if not text:
        return ""
    text = _SPEAKER_RE.sub("", text)
    text = _JAMO_SLANG_RE.sub(lambda m: _JAMO_SLANG[m.group(0)], text)
    text = _URL_RE.sub("", text)
    text = _EMAIL_RE.sub("", text)
    text = _HASHTAG_RE.sub("", text)
    text = _SINO_RANGE_RE.sub(_sino_range, text)
    text = _SINO_COUNTER_RE.sub(_force_sino, text)
    text = _JAMO_RE.sub("", text)
    text = text.replace("^", "")
    return text
