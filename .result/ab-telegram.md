# ab-telegram

## 1. 작업 결과

A/B 테스트 파이프라인 완전 통합 + telegram-bridge WaggleBot 파이프라인 명령 구현.

| 항목 | 파일 |
|------|------|
| A/B 변형 배정 — processor.py 통합 | `worker/ai_worker/core/processor.py` |
| AB_EVALUATE / AB_APPLY_WINNER JobType 추가 | `worker/db/models.py`, `backend/.../JobType.java` |
| AB 핸들러 추가 | `worker/dashboard_worker/handlers.py` |
| AB 백엔드 API 엔드포인트 | `backend/.../AnalyticsController.java` |
| AB 프론트엔드 API 클라이언트 | `frontend/lib/api/analytics.ts` |
| telegram config backendUrl 추가 | `telegram/src/config.ts` |
| WaggleBot API 클라이언트 신규 | `telegram/src/pipeline/wagglebot-api.ts` |
| 파이프라인 명령 모듈 신규 | `telegram/src/pipeline/pipeline-commands.ts` |
| /status, /posts, /approve, /reject, /crawl 명령 등록 | `telegram/src/bot/command-handler.ts` |
| MainMenu 파이프라인 버튼 추가 | `telegram/src/bot/keyboard.ts` |

## 2. 수정 내용

### A/B 테스트 파이프라인 통합
- `processor.py:process_with_retry` — PROCESSING 진입 직후 `assign_variant(post.id, session)` 호출 (retry_count=1 첫 시도에서만)
- variant_config의 `extra_instructions`는 이미 `_safe_generate_summary`에서 읽도록 구현되어 있었으므로 연결 완료
- `JobType`: `AB_EVALUATE`, `AB_APPLY_WINNER` 추가 (Python + Java 동기화)
- `handlers.py`: `_handle_ab_evaluate` (evaluate_group 호출), `_handle_ab_apply_winner` (apply_winner 호출)
- `AnalyticsController.java`: `POST /api/analytics/ab/evaluate`, `POST /api/analytics/ab/apply-winner` 추가
- `analytics.ts`: `abEvaluate(groupId)`, `abApplyWinner(groupId)` 추가

### telegram-bridge 파이프라인 명령
- `config.ts`: `backend.url` 추가 (`BACKEND_URL` env 또는 `http://backend:8080`)
- `wagglebot-api.ts` (신규): Spring Boot API 호출 — getPipelineStatus, getCollectedPosts, approvePost, rejectPost(`/decline`), triggerCrawl
- `pipeline-commands.ts` (신규): sendStatus, sendCollectedPosts(인라인 승인/거절 버튼), handleApprove, handleReject, handleCrawl
- `command-handler.ts`: `/status`, `/posts`, `/approve <id>`, `/reject <id>`, `/crawl` 명령 등록; callback `approve:`, `reject:`, `pipeline_*` 처리; HELP_TEXT 갱신
- `keyboard.ts`: MainMenu 재편 — 파이프라인 현황, 승인 대기, 크롤링 버튼 우선 배치

## 3. 테스트 결과물 저장 위치

정적 검증:
- `wagglebot-api.ts`: `/api/inbox/{id}/decline` 경로 일치 확인 (InboxController.java:57)
- `getCollectedPosts`: `{ posts: PostSummary[] }` 응답 형식 일치 (InboxController.java:25-47)
- `approve`: `POST /api/inbox/{id}/approve` ✓

## 4. 수동 테스트 방법

### A/B 테스트
```bash
# 1. ab_tests.json에 테스트 생성
docker compose -f env/docker-compose.yml exec ai_worker python -c "
from analytics.ab_test import create_test, list_tests
t = create_test('hook 스타일 테스트', 'hook_question', 'hook_exclamation')
print('생성됨:', t.group_id)
"
# 2. 게시글 승인 → 파이프라인 실행 → Content.variant_label 확인
# 3. AB_EVALUATE job enqueue (대시보드 또는 /api/analytics/ab/evaluate)
```

### telegram-bridge
```bash
# 환경변수 BACKEND_URL=http://backend:8080 설정 후 빌드
docker compose -f env/docker-compose.yml up -d telegram-bridge
# Telegram에서 /status 전송 → 파이프라인 현황 응답 확인
# /posts → 승인 대기 게시글 + 인라인 버튼 확인
```

## 5. 추천 commit message

```
feat: A/B 테스트 파이프라인 통합 + telegram-bridge 파이프라인 명령 구현

- processor.py: assign_variant() 호출 통합 (첫 시도에서만 A/B 변형 배정)
- JobType: AB_EVALUATE / AB_APPLY_WINNER 추가 (Python+Java 동기화)
- handlers.py: AB 평가/승자 반영 핸들러 추가
- AnalyticsController: POST /api/analytics/ab/evaluate, /apply-winner 추가
- analytics.ts: abEvaluate, abApplyWinner API 추가
- telegram: wagglebot-api.ts + pipeline-commands.ts 신규 구현
- telegram: /status, /posts, /approve, /reject, /crawl 명령 추가
- telegram: MainMenu 파이프라인 버튼 우선 배치
```
