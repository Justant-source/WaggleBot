# inbox-error-handling

## 1. 작업 결과

수신함 페이지 (`inbox/page.tsx`)에서 API 에러 핸들링 누락 버그 3개 수정.

- **Bug**: `handleBatchApprove`, `handleBatchDecline`, `handleCrawl` 핸들러에 try/catch 없음
  → API 호출 실패 시 `clearSelection()` + `load()` 미실행 → 선택 상태 고착, 목록 갱신 안 됨

## 2. 수정 내용

**파일:** `frontend/app/(admin)/admin/inbox/page.tsx`

```tsx
// 기존 (에러 시 clearSelection/load 미실행)
const handleBatchApprove = async () => {
  const ids = Array.from(selectedIds)
  if (!ids.length) return
  const result = await inboxApi.batch(ids, 'approve')  // 예외 발생 시 이후 코드 스킵
  ...
  clearSelection(); load()
}

// 수정 후
const handleBatchApprove = async () => {
  const ids = Array.from(selectedIds)
  if (!ids.length) return
  try {
    const result = await inboxApi.batch(ids, 'approve')
    ...
    clearSelection(); load()
  } catch { toast.error('일괄 승인 실패') }
}
```

수정 대상: `handleBatchApprove`, `handleBatchDecline`, `handleCrawl` (3개 핸들러)

## 3. 테스트 결과물 저장 위치

프론트엔드 빌드: `frontend/.next/`

## 4. 수동 테스트 방법

```bash
cd frontend && npm run dev
```

1. `http://localhost:3000/admin/inbox` 접속
2. 게시글 여러 개 체크박스 선택
3. 백엔드를 종료한 상태에서 "일괄 승인" 클릭
4. `toast.error('일괄 승인 실패')` 표시 확인 (선택 상태 유지됨)
5. 크롤링 버튼도 동일하게 에러 toast 확인

## 5. 추천 commit message

```
fix: 수신함 일괄 승인/거절/크롤링 API 에러 핸들링 추가
```

## 6. DOC-MAP 기준 갱신한 문서 목록

없음
