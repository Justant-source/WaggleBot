# json-parse-fix

## 1. 작업 결과

JSON 파싱 관련 버그 2건 추가 수정.

| 항목 | 파일 | 내용 |
|------|------|------|
| `ai_fitness` 핸들러 JSON 파싱 강화 | `handlers.py` | `[^}]+` 정규식 → `JSONDecoder.raw_decode()` 교체 |
| `VoiceCatalogService` 파싱 버그 | `VoiceCatalogService.java` | `{"voices":[…]}` 래퍼 처리 누락 수정 |

## 2. 수정 상세

### handlers.py — `_handle_ai_fitness`

**수정 전**: `re.search(r'\{[^}]+\}', raw, re.DOTALL)` — reason 필드에 `}` 문자 포함 시 JSONDecodeError 발생

**수정 후**:
```python
start = raw.find('{')
if start == -1:
    raise ValueError(...)
data, _ = json.JSONDecoder().raw_decode(raw, start)
```
- `raw_decode`는 첫 `{` 위치에서 중첩 구조까지 올바르게 파싱
- 불필요해진 `import re` 제거

### VoiceCatalogService.java

**loadVoices()**: `{"voices": [...]}` 래퍼를 먼저 `Map`으로 파싱 후 `voices` 배열 추출
**getPromptPresets()**: `{"presets": [...]}` 래퍼를 먼저 `Map`으로 파싱 후 `presets` 배열 추출
불필요해진 `LIST_REF` / `STR_LIST_REF` 상수 제거

## 3. 수동 테스트 방법

```
1. ai_fitness 파싱:
   reason에 특수문자/중괄호 포함 게시글로 AI 적합도 분석 실행
   → score/reason/recommended 정상 저장 확인

2. VoiceCatalogService:
   GET /api/tts/voices → "voices": [...] 목록 정상 반환 (기존: 항상 빈 리스트)
   GET /api/editor/prompt-presets → 프리셋 목록 정상 반환
```

## 4. 추천 commit message

```
fix: ai_fitness JSON raw_decode 강화, VoiceCatalogService 파싱 버그 수정
```
