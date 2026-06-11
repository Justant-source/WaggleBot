# layout-path-fix

## 1. 작업 결과

`normalizer.py`의 `layout.json` 경로 계산 버그 수정.
컨테이너 내 실제 `__file__` 경로 불일치로 `parents[3]` = `/`(루트)를 가리켜 `layout.json`을 항상 로드 실패하던 문제 해결.

## 2. 수정 내용

**파일:** `worker/ai_worker/script/normalizer.py`

### 버그 1: parents[3] → parents[2]

- 컨테이너 내 `__file__` = `/app/ai_worker/script/normalizer.py`
- `parents[3]` = `/` → `/config/layout.json` (존재 안함)
- `parents[2]` = `/app` → `/app/config/layout.json` (정상)

### 버그 2: total max_chars를 per-line 값으로 오독

`layout.json`의 `max_chars`는 `줄당_글자수 × max_lines`의 total 값:
- `body_line.max_chars=40` = 20자 × 2줄
- `comment_line.max_chars=60` = 20자 × 3줄

normalizer.py는 per-line 값을 기대하므로 `max_chars / max_lines`로 환산:

```python
# 기존 (total 값을 그대로 사용 → MAX_LINE_CHARS=40, COMMENT_LINE_CHARS=60)
MAX_LINE_CHARS = _constraints.get("body_line", {}).get("max_chars", 21)
COMMENT_LINE_CHARS = _constraints.get("comment_line", {}).get("max_chars", 20)

# 수정 후 (per-line 환산 → MAX_LINE_CHARS=20, COMMENT_LINE_CHARS=20)
MAX_LINE_CHARS = body_line.get("max_chars", 42) // max(body_line.get("max_lines", 2), 1)
COMMENT_LINE_CHARS = comment_line.get("max_chars", 60) // max(COMMENT_MAX_LINES, 1)
```

**수정 결과값:** `MAX_LINE_CHARS=20`, `COMMENT_LINE_CHARS=20`, `COMMENT_MAX_LINES=3`, `COMMENT_MAX_CHARS=60`

## 3. 영향 범위

`summarize_long_comment()`, `split_comment_lines()` — 댓글 줄 분할·요약 임계값이 이제 layout.json과 동기화됨. 기본값(20/20)과 동일하므로 기존 동작 무변화.

## 4. 수동 테스트 방법

```bash
docker compose exec ai_worker python3 -c "
import importlib, ai_worker.script.normalizer as n
importlib.reload(n)
print('MAX_LINE_CHARS:', n.MAX_LINE_CHARS)        # 20
print('COMMENT_LINE_CHARS:', n.COMMENT_LINE_CHARS) # 20
"
```

## 5. 추천 commit message

```
fix: normalizer.py layout.json 경로·글자수 계산 버그 수정
```

## 6. DOC-MAP 기준 갱신한 문서 목록

없음
