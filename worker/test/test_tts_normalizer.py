#!/usr/bin/env python3
"""TTS 정규화 테스트 — 앱 전처리(prenorm) + 발음 프로필 + 서버 정규화 골든.

구 ``normalizer.py``/``number_reader.py``(삭제)는 Local-TTS 서버 정규화(숫자·단위·월·범위·소수점)와
프로필 ``wagglebot/shorts-ko``(슬랭·영문 약어)로 대체됐다. 앱에는 ``prenorm.prenormalize`` 만 남는다.

- 오프라인: prenorm 단위, 프로필 YAML 구조, 골든의 prenorm 열
- 서버 필요(미도달 시 skip): 골든의 normalized 열 = 서버 ``jobs:dry_run`` 정규화 결과

실행: cd worker && PYTHONPATH=<repo>:<repo>/worker ../venv/bin/pytest test/test_tts_normalizer.py
"""
import json
import sys
from pathlib import Path

import pytest
import yaml

_ROOT = Path(__file__).resolve().parent.parent  # worker/
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from ai_worker.tts.prenorm import _sino, prenormalize as P  # noqa: E402

GOLDEN = json.loads((Path(__file__).parent / "data" / "tts_norm_golden.json").read_text(encoding="utf-8"))
PROFILE_PATH = _ROOT.parent / "config" / "tts_profile" / "shorts-ko.yaml"
SERVER_URL = "http://127.0.0.1:8500"


# ── prenorm: 앱 고유 규칙 ───────────────────────────────────────
def test_speaker_prefix_strip():
    assert P("댓글: 안녕") == "안녕"
    assert P("abc123: 안녕") == "안녕"


def test_jamo_slang_replaced():
    assert P("ㄹㅇ 대박") == "진짜 대박"
    assert P("ㅇㅋ ㄱㅅ") == "오케이 감사"


def test_laugh_and_jamo_removed():
    assert P("웃겨 ㅋㅋㅋ ㅎㅎ ㅠㅠ ^^").split() == ["웃겨"]
    assert "ㅋ" not in P("진짜ㅋㅋㅋㅋ 그래")


def test_jamo_only_becomes_blank():
    assert P("ㅋㅋㅋ").strip() == ""
    assert P("") == ""


def test_url_email_hashtag_removed():
    out = P("링크 https://a.b/c?x=1 메일 me@ex.com #태그 끝")
    assert "http" not in out and "@" not in out and "#" not in out
    assert out.split() == ["링크", "메일", "끝"]


def test_blank_line_structure_preserved():
    assert P("첫째.\n\n둘째.") == "첫째.\n\n둘째."


@pytest.mark.parametrize("text,expect", [
    ("50대", "오십 대"), ("4대 원칙", "사 대 원칙"), ("1대1", "일 대1"), ("10,000대", "만 대"),
    ("50~60대", "오십에서 육십 대"), ("암 4기", "암 사 기"), ("4기가", "4기가"), ("3대학", "삼 대학"),
])
def test_force_sino_counters(text, expect):
    assert P(text) == expect


def test_sino_numbers():
    assert [_sino(n) for n in (0, 1, 10, 100, 10000, 12345, 100000000, 150000000)] == [
        "영", "일", "십", "백", "만", "만이천삼백사십오", "일억", "일억오천만"]


# ── 프로필 YAML ────────────────────────────────────────────────
def test_profile_document_shape():
    doc = yaml.safe_load(PROFILE_PATH.read_text(encoding="utf-8"))
    assert doc["schema"] == "ltts.pronunciation/1"
    assert doc["profile"] == "wagglebot/shorts-ko"
    keys = [e["key"] for e in doc["entries"]]
    assert len(keys) == len(set(keys)), "키 중복"
    assert len(doc["tests"]) >= 20
    assert {"AI", "CCTV", "남친", "5G"} <= set(keys)


# ── 골든 ───────────────────────────────────────────────────────
def test_golden_prenorm_column():
    bad = [(c["input"], P(c["input"]), c["prenorm"]) for c in GOLDEN["cases"] if P(c["input"]) != c["prenorm"]]
    assert not bad, bad[:5]


def _server_up() -> bool:
    try:
        import httpx
        return httpx.get(f"{SERVER_URL}/healthz", timeout=2).status_code == 200
    except Exception:
        return False


@pytest.mark.skipif(not _server_up(), reason="Local-TTS 서버(127.0.0.1:8500) 미도달")
def test_golden_server_normalized():
    from ai_worker.tts.local_tts_client import InvalidRequest, LocalTTS
    cli = LocalTTS(SERVER_URL, client="wagglebot", max_retries=1)
    opts = {"normalize": {"enabled": True, "profile": GOLDEN["profile"], "return_text": True},
            "chunk": {"mode": "max_chars", "max_chars": 120}}
    bad = []
    for c in GOLDEN["cases"]:
        if not c["prenorm"].strip():
            continue
        try:
            got = cli.dry_run(c["prenorm"], opts).get("normalized_text") or ""
        except InvalidRequest:
            got = ""
        if got != c["normalized"]:
            bad.append((c["input"], got, c["normalized"]))
    assert not bad, bad[:5]
