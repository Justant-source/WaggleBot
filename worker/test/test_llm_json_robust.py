"""LLM JSON 파싱 견고성 + 콘텐츠 거부 처리 E2E 회귀 테스트.

배경 (버그):
    승인 → 확정 후 ai_worker 파이프라인이 "민감하지 않은 게시글"에도 간헐적으로
    FAILED 되는 현상. 근본 원인은 두 가지였다.
      1) call_llm_json이 ```json 코드펜스·트레일링 prose가 붙은 응답을 만나면
         json.loads가 깨지고, 탐욕적 정규식 폴백(r"\\{.*\\}")이 트레일링 텍스트의
         중괄호를 함께 삼켜 {} 를 반환 → chunk_with_llm이 'hook' 누락 ValueError.
      2) LLM이 콘텐츠를 거부(정치/민감)하면 {}가 반환되는데, 이를 기술적 실패와
         구분하지 못해 FAILED(재시도 대상)로 마킹.

수정:
    - transport.extract_json_object: 코드펜스 제거 + raw_decode(첫 '{'부터 한 객체만)
      로 트레일링 잡텍스트를 견고하게 흡수.
    - chunk_with_llm: 빈 dict는 LLMContentRefusalError로 승격.
    - core.main: LLMContentRefusalError는 DECLINED(재시도 안 함), 그 외만 FAILED.

실행:
    docker exec env-ai_worker-1 python -m pytest test/test_llm_json_robust.py -v
    docker exec env-ai_worker-1 python -m test.test_llm_json_robust   # 직접 실행
"""
import asyncio
import sys
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ---------------------------------------------------------------------------
# 1) extract_json_object — 순수 단위 (외부 서비스 불필요)
# ---------------------------------------------------------------------------
def test_extract_json_object_clean():
    from ai_worker.llm.transport import extract_json_object
    assert extract_json_object('{"hook": "a", "body": [], "closer": "z"}') == {
        "hook": "a", "body": [], "closer": "z"
    }


def test_extract_json_object_code_fence():
    """```json ... ``` 펜스를 벗겨낸다 (모델이 가장 자주 어기는 케이스)."""
    from ai_worker.llm.transport import extract_json_object
    raw = '```json\n{"hook": "a", "body": [1, 2], "closer": "z"}\n```'
    assert extract_json_object(raw) == {"hook": "a", "body": [1, 2], "closer": "z"}


def test_extract_json_object_fence_no_lang():
    from ai_worker.llm.transport import extract_json_object
    assert extract_json_object('```\n{"hook": "a"}\n```') == {"hook": "a"}


def test_extract_json_object_trailing_prose():
    """JSON 뒤에 모델이 덧붙인 설명문을 무시한다 (탐욕 정규식이 깨지던 케이스)."""
    from ai_worker.llm.transport import extract_json_object
    raw = '{"hook": "a", "closer": "z"}\n\n이 대본은 위와 같이 구성했습니다.'
    assert extract_json_object(raw) == {"hook": "a", "closer": "z"}


def test_extract_json_object_leading_prose():
    from ai_worker.llm.transport import extract_json_object
    raw = '다음은 요청하신 JSON입니다:\n{"hook": "a"}'
    assert extract_json_object(raw) == {"hook": "a"}


def test_extract_json_object_fenced_with_trailing_prose():
    from ai_worker.llm.transport import extract_json_object
    raw = '```json\n{"hook": "x"}\n```\n설명: 위 대본은 후킹을 강화했습니다.'
    assert extract_json_object(raw) == {"hook": "x"}


def test_extract_json_object_nested_braces():
    """본문 문자열·중첩 객체 안의 중괄호가 있어도 정확히 파싱한다."""
    from ai_worker.llm.transport import extract_json_object
    raw = '{"hook": "a {b} c", "body": [{"line_count": 1, "lines": ["x}y"]}], "closer": "z"}'
    obj = extract_json_object(raw)
    assert obj["hook"] == "a {b} c"
    assert obj["body"][0]["lines"] == ["x}y"]


def test_extract_json_object_refusal_returns_empty():
    """JSON이 전혀 없는 거부/메타 응답은 빈 dict (상위에서 거부 처리)."""
    from ai_worker.llm.transport import extract_json_object
    assert extract_json_object("이 요청은 처리할 수 없습니다.") == {}
    assert extract_json_object("") == {}
    assert extract_json_object("   \n  ") == {}


def test_extract_json_object_second_object_ignored():
    """JSON 뒤에 예시용 두 번째 객체가 붙어도 첫 객체만 취한다."""
    from ai_worker.llm.transport import extract_json_object
    raw = '{"hook": "real"}\n\nNote (예시): {"hook": "example"}'
    assert extract_json_object(raw) == {"hook": "real"}


def test_extract_json_object_prose_braces_before_json():
    """JSON '앞' prose에 리터럴 중괄호가 섞여 있어도 실제 객체를 찾는다."""
    from ai_worker.llm.transport import extract_json_object
    raw = '아래 {중요} 형식의 대본입니다:\n{"hook": "real", "closer": "z"}'
    assert extract_json_object(raw) == {"hook": "real", "closer": "z"}


# ---------------------------------------------------------------------------
# 2) call_llm_json — call_llm 모킹 (외부 서비스 불필요)
# ---------------------------------------------------------------------------
def test_call_llm_json_strips_fence(monkeypatch):
    import ai_worker.llm.transport as T
    monkeypatch.setattr(
        T, "call_llm",
        lambda *a, **k: '```json\n{"hook": "h", "body": [], "closer": "c"}\n```',
    )
    out = T.call_llm_json("prompt", call_type="chunk")
    assert out == {"hook": "h", "body": [], "closer": "c"}


def test_call_llm_json_refusal_returns_empty(monkeypatch):
    import ai_worker.llm.transport as T
    monkeypatch.setattr(T, "call_llm", lambda *a, **k: "이 요청은 처리할 수 없습니다.")
    assert T.call_llm_json("prompt", call_type="chunk") == {}


# ---------------------------------------------------------------------------
# 3) chunk_with_llm — 콘텐츠 거부 → LLMContentRefusalError (DECLINED 유발)
# ---------------------------------------------------------------------------
def _make_profile():
    import dataclasses
    from ai_worker.scene.analyzer import ResourceProfile
    kwargs = {}
    for f in dataclasses.fields(ResourceProfile):
        if f.default is dataclasses.MISSING and f.default_factory is dataclasses.MISSING:
            kwargs[f.name] = "text_heavy" if f.name == "strategy" else 0
    return ResourceProfile(**kwargs)


def test_chunk_refusal_raises_refusal_error(monkeypatch):
    """LLM이 빈 응답(거부)을 주면 ValueError가 아닌 LLMContentRefusalError가 떠야
    상위에서 DECLINED로 분기된다."""
    import ai_worker.script.chunker as C
    from ai_worker.llm.transport import LLMContentRefusalError

    monkeypatch.setattr(C, "_call_llm_json_sync", lambda *a, **k: {})

    async def run():
        return await C.chunk_with_llm("본문", _make_profile(), post_id=None, extended=True)

    try:
        asyncio.run(run())
        assert False, "LLMContentRefusalError가 발생해야 함"
    except LLMContentRefusalError:
        pass  # 기대 동작


def test_chunk_valid_returns_script(monkeypatch):
    """정상 JSON이면 hook/body/closer가 채워진 dict를 반환한다."""
    import ai_worker.script.chunker as C

    valid = {
        "hook": "후킹 문장",
        "body": [{"line_count": 1, "lines": ["문장1"]}],
        "closer": "마무리",
        "mood": "daily",
    }
    monkeypatch.setattr(C, "_call_llm_json_sync", lambda *a, **k: dict(valid))

    async def run():
        return await C.chunk_with_llm("본문", _make_profile(), post_id=None, extended=True)

    out = asyncio.run(run())
    assert out["hook"] == "후킹 문장"
    assert isinstance(out["body"], list) and out["body"]
    assert out["closer"] == "마무리"


# ---------------------------------------------------------------------------
# 직접 실행 (pytest 없이) — docker exec ... python -m test.test_llm_json_robust
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import types

    class _MP:
        """pytest monkeypatch 최소 대체 — setattr 후 복원."""
        def __init__(self): self._undo = []
        def setattr(self, obj, name, val):
            self._undo.append((obj, name, getattr(obj, name)))
            setattr(obj, name, val)
        def undo(self):
            for obj, name, val in reversed(self._undo):
                setattr(obj, name, val)
            self._undo = []

    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and isinstance(f, types.FunctionType)]
    passed = failed = 0
    for name, fn in tests:
        mp = _MP()
        try:
            import inspect
            if "monkeypatch" in inspect.signature(fn).parameters:
                fn(mp)
            else:
                fn()
            print(f"  [PASS] {name}")
            passed += 1
        except Exception as e:
            import traceback
            print(f"  [FAIL] {name}: {type(e).__name__}: {e}")
            traceback.print_exc()
            failed += 1
        finally:
            mp.undo()
    print(f"\n=== {passed} passed, {failed} failed / {len(tests)} ===")
    sys.exit(1 if failed else 0)
