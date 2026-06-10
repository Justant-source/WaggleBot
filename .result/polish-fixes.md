# polish-fixes

## 1. 작업 결과

6개 파일에서 버그 수정 + UI 개선 작업.

| 항목 | 파일 |
|------|------|
| TTS 프리뷰 오디오 경로 버그 수정 | `frontend/app/(admin)/admin/editor/[postId]/page.tsx` |
| LLM 이력 callType/success 필터 + 행 펼치기 | `frontend/app/(admin)/admin/llm-logs/page.tsx` |
| settings — llm_model_overrides textarea, use_content_processor 토글 추가 | `frontend/app/(admin)/admin/settings/page.tsx` |
| TypeScript JobType에 AB_* 추가, PipelineSettings boolean 필드 추가 | `frontend/lib/types/index.ts` |
| Jackson 날짜 직렬화 명시 설정 | `backend/src/main/resources/application.yml` |
| Java SettingsService 기본값 동기화 | `backend/src/main/java/com/wagglebot/settings/SettingsService.java` |

## 2. 수정 내용

### TTS 오디오 경로 버그 (editor/[postId]/page.tsx)
- 기존: `audioRef.src = /media/tmp/preview_${id}.mp3` — 확장자 하드코딩 (실제 TTS 출력은 `.wav`)
- 수정: `preview_path` job 결과값에서 경로 추출 → `/media/${path.replace('/app/media/', '')}`
- TTS 오류 시 `toast.error('TTS 생성 실패')` 추가 (기존에 에러 핸들링 없음)

### LLM 이력 필터 + 행 펼치기 (llm-logs/page.tsx)
- callType 드롭다운: 전체 / chunk / generate_script / scene_director / video_prompt / translate / comment_summarize / feedback
- 성공/실패 필터 드롭다운
- 행 클릭 시 펼치기: errorMessage(빨간 박스), promptText(접기/펼치기), rawResponse(접기/펼치기)
- 필터 변경 시 page=0으로 자동 리셋

### settings 페이지 추가 필드 (settings/page.tsx)
- `llm_model_overrides`: JSON textarea — callType별 모델 오버라이드 (`{"chunk": "sonnet", ...}`)
- `use_content_processor`: 토글 스위치 — 8-Phase 파이프라인 활성화 여부
  - ON: chunk_with_llm + SceneDirector 경로 사용
  - OFF: 레거시 `generate_script()` 경로 사용 (기본값)

### TypeScript 타입 보완 (types/index.ts)
- `JobType` union에 `AB_CREATE | AB_EVALUATE | AB_APPLY_WINNER` 추가
- `PipelineSettings`에 `auto_approve_enabled`, `auto_approve_threshold`, `auto_upload` 타입 명시

### Jackson 날짜 직렬화 (application.yml)
- `spring.jackson.serialization.write-dates-as-timestamps: false` 명시
- `LocalDateTime`이 ISO 문자열로 직렬화됨 (progress 페이지의 `new Date(updatedAt)` 올바르게 동작)

### Java SettingsService 기본값 (SettingsService.java)
- 기존: `max_body_items: 23` 같은 잘못된 값 포함, `auto_approve_enabled/auto_upload/use_content_processor` 누락
- 수정: Python `_PIPELINE_DEFAULTS`와 동기화 (`"false"` 문자열 형식 일치)

## 3. 수동 테스트 방법

### TTS 프리뷰
```
1. 에디터에서 대본이 있는 게시글 열기
2. "TTS 미리듣기" 클릭
3. 생성 완료 후 오디오 플레이어에서 재생 확인 (.wav 형식)
```

### LLM 이력 필터
```
1. /admin/llm-logs 접속
2. callType 드롭다운에서 "chunk" 선택 → 청킹 로그만 표시
3. 성공/실패 드롭다운에서 "실패만" 선택
4. 행 클릭 → 프롬프트/응답 펼치기 확인
```

### settings 새 필드
```
1. /admin/settings 접속
2. "LLM 모델" 섹션에 모델 오버라이드 JSON 텍스트박스 확인
3. "파이프라인" 섹션에 "8-Phase 파이프라인" 토글 확인
4. 저장 → config/pipeline.json에 llm_model_overrides, use_content_processor 저장 확인
```

## 4. 추천 commit message

```
fix: TTS 프리뷰 .mp3 하드코딩 버그 수정 + llm-logs 필터/행펼치기 + settings 고급 필드 추가

- editor: TTS preview_path에서 실제 확장자(.wav) 추출 (하드코딩 .mp3 버그 수정)
- llm-logs: callType/success 필터 드롭다운 + 행 클릭 시 prompt/response 펼치기
- settings: llm_model_overrides textarea + use_content_processor(8-Phase) 토글 추가
- types: JobType에 AB_* 추가, PipelineSettings boolean 필드 명시
- backend: jackson write-dates-as-timestamps=false 명시, SettingsService 기본값 동기화
```
