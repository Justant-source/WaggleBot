# dashboard-ux

## 1. 작업 결과

대시보드 3가지 UX 개선 — settings 자동화 토글, analytics 성과 테이블, A/B 테스트 생성 UI 구현.

| 항목 | 파일 |
|------|------|
| Switch 컴포넌트 신규 | `frontend/components/ui/switch.tsx` |
| settings — auto_approve_enabled/auto_upload 토글 | `frontend/app/(admin)/admin/settings/page.tsx` |
| analytics — YouTube 성과 테이블 | `frontend/app/(admin)/admin/analytics/page.tsx` |
| analytics — A/B 테스트 생성/평가 UI 개선 | `frontend/app/(admin)/admin/analytics/page.tsx` |
| analytics API — performance, abCreate 추가 | `frontend/lib/api/analytics.ts` |
| AnalyticsController — /performance, /ab/create 추가 | `backend/.../AnalyticsController.java` |
| AB_CREATE JobType + 핸들러 | `worker/db/models.py`, `worker/dashboard_worker/handlers.py` |

## 2. 수정 내용

### Switch 컴포넌트
- `components/ui/switch.tsx` — Tailwind 기반 토글 스위치. `checked` prop으로 상태 제어, react-hook-form `Controller`와 연동

### settings 페이지
- 스키마에 `auto_approve_enabled: z.boolean()`, `auto_upload: z.boolean()` 추가
- 각각 `Switch` 컴포넌트로 렌더링 (react-hook-form `Controller` 사용)
- `auto_approve_enabled=true` 시에만 임계값 입력 필드 표시 (조건부 렌더링)
- `onSubmit`에서 boolean → `"true"/"false"` 문자열 변환 (pipeline.json은 문자열 저장)
- 로드 시 `cfg.auto_approve_enabled === 'true'` 조건으로 파싱

### analytics 페이지
- **YouTube 성과 테이블**: `analyticsApi.performance()` 호출 → 조회수/좋아요/댓글 표시, video_id 있으면 YouTube 링크
- **A/B 테스트 생성 폼**: 테스트 이름 + 프리셋 A/B 드롭다운 (6가지: hook_question/exclamation, body_short/narrative, tone_formal/casual)
  - 생성 성공 시 Group ID가 평가 입력란에 자동 복사
- **A/B 평가 섹션**: 기존 단일 섹션 → "생성"과 "평가" 두 섹션으로 분리

### 백엔드
- `GET /api/analytics/performance?limit=20` — UPLOADED 포스트 + upload_meta.youtube.analytics 추출
- `POST /api/analytics/ab/create` — AB_CREATE job enqueue
- `AB_CREATE` JobType (Python/Java 동기화)
- `_handle_ab_create`: `create_test(name, preset_a, preset_b)` 호출 → group_id 반환

## 3. 수동 테스트 방법

### settings — auto_approve 토글
```
1. 대시보드 /admin/settings 접속
2. "자동화" 섹션에서 "자동 승인" 토글 ON
3. 임계값 입력 필드 표시 확인
4. 저장 → config/pipeline.json의 auto_approve_enabled=true 확인
```

### analytics — 성과 테이블
```
1. UPLOADED 상태 게시글 + upload_meta에 youtube.analytics 데이터 있어야 함
2. collect_analytics() 실행 후 /admin/analytics 접속
3. "YouTube 성과" 섹션에 조회수/좋아요/댓글 테이블 표시 확인
```

### A/B 테스트 생성
```
1. /admin/analytics → "A/B 테스트 생성" 섹션
2. 이름 입력 + 프리셋 A/B 선택 → "테스트 생성" 클릭
3. 생성된 group_id가 평가 섹션에 자동 입력 확인
4. config/ab_tests.json에 새 테스트 추가됨 확인
```

## 4. 추천 commit message

```
feat: dashboard UX 개선 — settings 자동화 토글 + analytics 성과 테이블 + A/B 생성 UI

- Switch 컴포넌트 신규 (Tailwind 토글)
- settings: auto_approve_enabled/auto_upload 토글 추가
- analytics: YouTube 성과 테이블 (조회수/좋아요/댓글)
- analytics: A/B 테스트 생성 폼 (프리셋 드롭다운) + 생성/평가 섹션 분리
- AnalyticsController: GET /performance, POST /ab/create 추가
- AB_CREATE JobType + 핸들러 추가 (Python/Java 동기화)
```
