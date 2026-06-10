# p2-improve — transport 헤더 조건부 + 배치 실패 표시

## 1. 작업 결과

두 가지 P2 개선을 완료.

- **변경 1**: `transport.py` API 헤더를 조건부로 구성. 공식 Anthropic 도메인이면 `x-api-key`만, 커스텀 proxy URL이면 `Authorization: Bearer`도 추가.
- **변경 2**: `InboxController` batch 메서드가 개별 실패를 `failed` 목록에 수집해 반환. 프론트엔드는 `failed` 배열이 있으면 `toast.warning`으로 성공/실패 수를 표시.

## 2. 수정 내용

### worker/ai_worker/llm/transport.py
- 모듈 상수 추가: `_ANTHROPIC_OFFICIAL_DOMAIN = "https://api.anthropic.com"`
- `_build_api_headers(api_key, base_url) -> dict` 함수 신설
  - `base_url`이 `https://api.anthropic.com`으로 시작하면 `x-api-key`만 포함
  - 그 외(프록시/게이트웨이)면 `authorization: Bearer <key>`도 추가
- `_call_via_api()` 내 하드코딩 헤더 블록 → `_build_api_headers()` 호출로 교체
- 사용되지 않게 된 `_build_messages_url()` 인라인화 (base_url + "/messages" 직접 사용)

### backend/src/main/java/com/wagglebot/controller/InboxController.java
- `batch()` 메서드: `count` 단일 카운터 → `processed` + `failed List<Map>` 분리
- catch 블록에서 `{id, error}` 맵 생성해 `failed` 목록에 추가 (전체 400 반환 없음, 부분 성공 허용)
- 응답 구조: `{processed: N, failed: [{id, error}, ...], action: "approve"}`

### frontend/lib/api/inbox.ts
- `batch()` 반환 타입을 `{ processed: number; failed: Array<{ id: number; error: string }>; action: string }`로 갱신

### frontend/app/(admin)/admin/inbox/page.tsx
- `handleBatchApprove()`: `result.failed?.length > 0`이면 `toast.warning(...)`, 모두 성공이면 기존 `toast.success(...)`

## 3. 테스트 결과물 저장 위치

별도 산출물 없음 (소스 수정만).

## 4. 수동 테스트 방법

### 변경 1 (transport 헤더)
1. `LLM_BACKEND=api` + `ANTHROPIC_API_KEY` 설정 후 LLM 호출 → Anthropic API 정상 응답 확인 (기존과 동일, `x-api-key`만 전송)
2. `ANTHROPIC_BASE_URL=https://proxy.example.com/v1`로 설정 후 호출 → 요청 헤더에 `authorization: Bearer ...`도 포함되는지 디버그 로그 확인

### 변경 2 (배치 실패 표시)
1. 수신함에서 존재하지 않거나 이미 처리된 게시글 ID를 포함해 일괄 승인 실행
2. 응답 JSON `{ processed: N, failed: [...] }` 확인
3. 프론트엔드 토스트: 일부 실패 시 "N개 성공, M개 실패" 경고, 전부 성공 시 "N개 승인"

## 5. 추천 commit message

```
fix: transport API 헤더 조건부 처리 + 배치 승인 실패 표시

- transport._build_api_headers(): Anthropic 공식 도메인이면 x-api-key만,
  커스텀 proxy면 Authorization: Bearer도 추가
- InboxController.batch(): silently-ignored 예외를 failed 목록으로 수집,
  {processed, failed[], action} 응답 반환 (부분 성공 허용)
- frontend handleBatchApprove: failed 배열 있으면 toast.warning으로 표시
```
