#!/usr/bin/env python3
"""TTS 한국어 정규화 단위 테스트 (오프라인 — fish-speech 불필요).

실행 (ai_worker 컨테이너):
    docker compose -f env/docker-compose.yml exec ai_worker pytest test/test_tts_normalizer.py -v
    docker compose -f env/docker-compose.yml exec ai_worker python test/test_tts_normalizer.py
"""
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent  # /app (worker/)
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from ai_worker.tts.normalizer import normalize_for_tts as N
from ai_worker.tts import number_reader as NR


# ── 숫자: 소수 / 퍼센트 / 콤마 ──────────────────────────────────
def test_decimal():
    assert "삼 점 오" in N("3.5초 걸렸다")

def test_decimal_percent():
    assert "오십 점 오 퍼센트" in N("50.5% 할인")

def test_comma_number():
    out = N("1,200,000원")
    assert "백이십만" in out and "," not in out

def test_sentence_period_not_decimal():
    # 문장 끝 마침표는 소수로 오인하지 않음
    out = N("가격은 3000원. 끝.")
    assert "삼천 원" in out


# ── 숫자: 범위 / 월 / 전화 / 단위 ───────────────────────────────
def test_range_sino():
    # 년 = 한자어 카운터 → sino
    assert "삼에서 사 년" in N("3~4년 후")

def test_range_no_counter():
    assert "삼에서 사" in N("3~4 정도")

def test_range_native_counter():
    assert "세에서 네 명" in N("3~4명 참석")

def test_month_irregular():
    out = N("6월과 10월")
    assert "유월" in out and "시월" in out

def test_month_regular():
    assert "삼 월" in N("3월에 만나요") or "삼월" in N("3월에 만나요")

def test_phone_hyphen():
    out = N("010-1234-5678로 연락")
    assert "공 일 공" in out and "-" not in out

def test_metric_units():
    out = N("175cm 70kg")
    assert "백칠십오 센티미터" in out and "칠십 킬로그램" in out

def test_metric_decimal():
    assert "삼 점 오 킬로미터" in N("3.5km 거리")

def test_data_unit():
    assert "기가바이트" in N("5GB 용량")


# ── 약어 (slang_map.json 병합) ─────────────────────────────────
def test_acronyms():
    out = N("CCTV와 SNS")
    assert "씨씨티비" in out and "에스엔에스" in out

def test_acronym_ai():
    assert "에이아이" in N("AI 기술")

def test_slang_builtin_preserved():
    # 내장 슬랭(ㄹㅇ)이 JSON 병합 후에도 살아있어야 함
    assert "진짜" in N("ㄹㅇ 대박")

def test_acronym_no_substring_collision():
    # 5GB 내부 '5G'가 '오지'로 잘못 치환되지 않음 (데이터 단위로 처리)
    out = N("5GB 메모리")
    assert "오지" not in out


# ── 조사 교정 스코프 (흔한 단어 보존) ──────────────────────────
def test_common_words_preserved():
    # 전역 fix_particles 버그였던 단어들 — 망가지면 안 됨
    assert "마을" in N("마을 사람들")
    assert "가을" in N("가을 하늘")
    assert "사과" in N("사과 두 개")

def test_slang_particle_fixed():
    assert "남자친구와" in N("남친과 헤어졌어")
    assert "남자친구가" in N("남친이 생겼어")

def test_slang_particle_jongseong():
    # 받침 있는 치환 결과는 받침 조사 유지
    assert "베스트 댓글을" in N("베댓을 봤다")


# ── 웃음 마커 게이트 ───────────────────────────────────────────
def test_laugh_marker_off_default():
    # 기본 off: ㅋㅋ 삭제
    out = N("웃겨 ㅋㅋㅋ")
    assert "(laughing)" not in out

def test_laugh_marker_on():
    out = N("웃겨 ㅋㅋㅋ", laugh_marker=True)
    assert "(laughing)" in out

def test_laugh_marker_survives_normalization():
    # 마커가 정규화 뒷단계(따옴표 제거 등)에 삭제되지 않아야 함
    out = N("진짜 ㅎㅎㅎ 그래", laugh_marker=True)
    assert "(laughing)" in out


# ── 가드: 빈 텍스트 / 마침표 ───────────────────────────────────
def test_speaker_prefix_strip():
    assert not N("ㅇㅇ: 안녕").startswith("ㅇㅇ")

def test_final_period_added():
    assert N("안녕하세요").endswith(".")

def test_jamo_only_becomes_empty():
    # 자음만 → 정규화 후 사실상 빈 텍스트 (마침표만 남거나 빈 문자열)
    out = N("ㅋㅋㅋ").strip().rstrip(".")
    assert out == ""


# ── number_reader 직접 ─────────────────────────────────────────
def test_read_digits():
    assert NR.read_digits("010") == "공 일 공"

def test_sino_number():
    assert NR.sino_number(12345) == "일만이천삼백사십오"

def test_native_number():
    assert NR.native_number(3) == "세"


def _run_all() -> int:
    """pytest 없이 직접 실행 시 모든 test_ 함수 수행."""
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {fn.__name__}: {e}")
        except Exception as e:
            failed += 1
            print(f"ERROR {fn.__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_run_all())
