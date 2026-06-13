# llm-calltypes — LLM 이력 callType 필터 동적화

## 1. 작업 결과

LLM 이력 페이지의 callType 필터 드롭다운이 7개 하드코딩에서
**백엔드 DB distinct 조회로 동적 로드**되도록 변경됐다.

기존 하드코딩에서 빠진 신규 call_type들이 필터에 자동 반영된다:
- `generate_script_auto`, `generate_script_editor`
- `video_prompt_t2v`, `video_prompt_i2v`, `video_prompt_simplify`
- `video_visual_anchor`, `video_image_brief`

## 2. 수정 내용

| 파일 | 변경 내용 |
|------|----------|
| `backend/.../domain/LlmLogRepository.java` | `findDistinctCallTypes()` JPQL distinct 쿼리 추가 |
| `backend/.../controller/LlmLogController.java` | `GET /api/llm-logs/call-types` 엔드포인트 추가 |
| `frontend/lib/api/llmLogs.ts` | `callTypes()` API 호출 추가 |
| `frontend/app/(admin)/admin/llm-logs/page.tsx` | `CALL_TYPES` 상수 제거, `useState<string[]>([])` + 마운트 `useEffect` 추가, Select 드롭다운 동적 렌더링 |

## 3. 테스트 결과물 위치

```bash
curl http://localhost:8080/api/llm-logs/call-types
# → ["chunk","comment_summarize","generate_script_auto","generate_script_editor",
#    "scene_director","video_image_brief","video_prompt_i2v","video_prompt_simplify",
#    "video_prompt_t2v","video_visual_anchor"]
```

하드코딩 7개 → DB 실제 10개 call_type 반환 확인.

## 4. 수동 테스트 방법

1. 브라우저 `http://localhost:3000/admin/llm-logs` 접속
2. callType 필터 드롭다운 클릭 → video_prompt_t2v, video_visual_anchor 등 표시 확인
3. 각 call_type 선택 시 해당 로그만 필터링되는지 확인

## 5. 추천 commit message

```
feat: LLM 이력 callType 필터 동적화 (CALL_TYPES 하드코딩 제거)

GET /api/llm-logs/call-types → llm_logs.call_type distinct 조회.
video_prompt_t2v·video_visual_anchor 등 신규 call_type 자동 반영.
```

## 6. DOC-MAP 기준 갱신한 문서 목록

없음 — UI 필터 개선으로 docs/ SSOT 범위 밖.
