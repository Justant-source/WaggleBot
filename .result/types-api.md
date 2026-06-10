# 작업 결과: 프론트엔드 타입 & API 레이어

## 1. 작업 결과
대시보드 대개편에 필요한 타입 정의 및 API 클라이언트 레이어를 모두 추가/수정 완료.

## 2. 수정 내용

### `frontend/lib/types/index.ts`
- `Post` 인터페이스에 AI 분석 필드 추가: `aiScore`, `aiReason`, `aiRecommended`, `aiAnalyzedAt`
- `Content` 인터페이스에 TTS/생성 필드 추가: `ttsVoice`, `genInstructions`
- 신규 타입 6종 추가:
  - `VoiceInfo` — TTS 보이스 목록 항목
  - `PromptPreset` — 대본 생성 프리셋
  - `PostProgress` — 파이프라인 진행 상황 (phase, scenesDone 등)
  - `ProcessingPost extends Post` — 진행 중인 게시글 + progress 포함
  - `OverviewData` — 대시보드 개요 API 응답 구조

### `frontend/lib/api/inbox.ts`
- `list` 파라미터를 `InboxListParams` 인터페이스로 교체 (신규: `sort`, `since`, `recommended` 필드)
- `comments(id, limit)` 함수 추가 — 게시글 댓글 목록
- `analyzeBatch(params)` 함수 추가 — 일괄 AI 분석 enqueue

### `frontend/lib/api/editor.ts`
- `EditorPostDetail` 인터페이스에 필드 추가: `ttsVoice`, `genInstructions`, `variantGroup`, `variantLabel`
- `PromptPreset` import 추가
- `setVoice(id, voice)` 함수 추가 — 개별 TTS 보이스 설정
- `promptPresets()` 함수 추가 — 대본 생성 프리셋 목록 조회

### `frontend/lib/api/progress.ts`
- `ProcessingPost` import 추가
- `get()` 반환 타입의 `processing` 필드를 `Post[]` → `ProcessingPost[]`로 변경

### `frontend/lib/api/tts.ts` (신규)
- `ttsApi.voices()` — `/api/tts/voices` GET, `{ defaultVoice, voices: VoiceInfo[] }` 반환

### `frontend/lib/api/overview.ts` (신규)
- `overviewApi.get(since?)` — `/api/overview` GET, `OverviewData` 반환

### `frontend/lib/nav-config.ts`
- `LayoutDashboard` import 추가
- NAV_GROUPS 운영 섹션 맨 앞에 `{ href: '/admin/overview', label: '대시보드', icon: LayoutDashboard }` 추가

### `frontend/app/page.tsx`
- 루트 리다이렉트 `/admin/inbox` → `/admin/overview` 변경

## 3. 테스트 결과물 저장 위치
해당 없음 (타입/API 레이어 변경, 런타임 테스트 불필요)

## 4. 수동 테스트 방법
```bash
cd frontend && npx tsc --noEmit
```
타입 에러 0건 확인.

## 5. 추천 commit message
```
feat: 프론트엔드 타입 & API 레이어 — overview/tts 신규, inbox/editor/progress 확장
```
