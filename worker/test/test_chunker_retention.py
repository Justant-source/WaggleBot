"""청킹 프롬프트 리텐션 개편 + 입력 격차 수정 검증 테스트.

검증 체크리스트:
- [x] create_chunking_prompt가 title/best_comments/extra_instructions 섹션을 user tail에 포함
- [x] 인자 미전달 시(하위호환) 기존처럼 동작 — 추가 섹션 없음
- [x] build_chunking_system이 리텐션 7개 기법(2-1~2-7) + 자가점검을 포함
- [x] few-shot 예시 JSON이 유효하고 길이 제약(hook 40 / 본문·closer 20)을 지킴
- [x] 본문 절단이 4000자(레거시와 통일)
- [x] call_llm_json이 temperature 파라미터를 수용
"""
import inspect
import json
import re
import sys
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _make_profile():
    from ai_worker.scene.analyzer import ResourceProfile
    import dataclasses
    kwargs = {}
    for f in dataclasses.fields(ResourceProfile):
        if f.default is dataclasses.MISSING and f.default_factory is dataclasses.MISSING:
            kwargs[f.name] = "balanced" if f.name == "strategy" else 0
    return ResourceProfile(**kwargs)


def test_user_tail_includes_new_sections():
    """제목·베스트 댓글·추가 지시가 user tail에 주입되는지."""
    from ai_worker.script.chunker import create_chunking_prompt

    prof = _make_profile()
    p = create_chunking_prompt(
        "본문 내용입니다", prof, extended=True,
        title="커뮤니티 인기글 제목",
        best_comments=["닉1: 사이다 댓글", "닉2: 정보 댓글"],
        extra_instructions="성과 분석 기반 선호 mood: shock",
    )
    assert "- 제목: 커뮤니티 인기글 제목" in p
    assert "## 베스트 댓글" in p and "- 닉1: 사이다 댓글" in p
    assert "## 추가 지시사항" in p and "성과 분석 기반 선호 mood: shock" in p
    print("PASS: test_user_tail_includes_new_sections")


def test_user_tail_backward_compat():
    """인자 미전달 시 추가 섹션이 없어야 한다(하위호환).

    system 프롬프트의 few-shot 예시에도 '- 제목:'/'베스트 댓글'이 등장하므로,
    검사는 동적 user tail(마지막 '## 자원 상황' 이후)로 한정한다.
    """
    from ai_worker.script.chunker import create_chunking_prompt

    prof = _make_profile()
    p = create_chunking_prompt("본문만", prof, extended=True)
    tail = p[p.rfind("## 자원 상황"):]
    assert "## 베스트 댓글" not in tail
    assert "## 추가 지시사항" not in tail
    assert "- 제목:" not in tail  # 제목 미전달 시 라인 자체가 없음
    print("PASS: test_user_tail_backward_compat")


def test_body_truncation_4000():
    """본문 절단이 4000자(레거시와 통일)인지."""
    from ai_worker.script.chunker import create_chunking_prompt

    prof = _make_profile()
    long_body = "가" * 5000
    p = create_chunking_prompt(long_body, prof)
    assert "가" * 4000 in p
    assert "가" * 4001 not in p
    print("PASS: test_body_truncation_4000")


def test_system_has_retention_sections():
    """리텐션 7개 기법 + 자가점검 + 목표 함수가 system 프롬프트에 있는지."""
    from ai_worker.script.chunker import build_chunking_system

    s = build_chunking_system(extended=True)
    for tag in ["2-1", "2-2", "2-3", "2-4", "2-5", "2-6", "2-7", "자가점검", "마지막 1초"]:
        assert tag in s, f"리텐션 섹션 누락: {tag}"
    print("PASS: test_system_has_retention_sections")


def test_fewshot_example_valid():
    """few-shot 예시 JSON이 유효하고 길이 제약을 지키는지."""
    from ai_worker.script.chunker import build_chunking_system
    from config.settings import MAX_HOOK_CHARS, MAX_BODY_CHARS

    s = build_chunking_system(extended=True)
    idx = s.find("[이상적 출력]")
    sub = s[idx:]
    start = sub.find("{")
    depth = 0
    block = None
    for i, ch in enumerate(sub[start:]):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                block = sub[start:start + i + 1]
                break
    assert block is not None, "예시 JSON 블록을 찾지 못함"
    parsed = json.loads(block)  # 유효한 JSON이어야 함
    for key in ("hook", "body", "closer", "title_suggestion", "tags", "mood"):
        assert key in parsed, f"예시 JSON 키 누락: {key}"
    assert len(parsed["hook"]) <= MAX_HOOK_CHARS
    assert len(parsed["closer"]) <= MAX_BODY_CHARS
    over = [
        l for b in parsed["body"]
        for l in b.get("lines", [])
        if b.get("type") != "comment" and len(l) > MAX_BODY_CHARS
    ]
    assert not over, f"본문 줄 길이 초과: {over}"
    assert sum(1 for b in parsed["body"] if b.get("type") == "comment") >= 3
    print("PASS: test_fewshot_example_valid")


def test_call_llm_json_accepts_temperature():
    """call_llm_json이 temperature 파라미터를 수용하는지."""
    from ai_worker.llm.transport import call_llm_json
    assert "temperature" in inspect.signature(call_llm_json).parameters
    print("PASS: test_call_llm_json_accepts_temperature")


if __name__ == "__main__":
    test_user_tail_includes_new_sections()
    test_user_tail_backward_compat()
    test_body_truncation_4000()
    test_system_has_retention_sections()
    test_fewshot_example_valid()
    test_call_llm_json_accepts_temperature()
    print("\n=== ALL TESTS PASSED ===")
