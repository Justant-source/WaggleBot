# gallery-pagination

## 1. 작업 결과

전체 코드 스캔 완료. 갤러리 페이지에서 버그 2개 발견 및 수정:

- **Bug 1**: `page`/`setPage` 상태가 존재하지만 페이지네이션 UI 없음 → 항상 첫 페이지만 표시
- **Bug 2**: HD렌더/업로드 API 호출이 fire-and-forget — 실패 시 에러 toast 없음

## 2. 수정 내용

**파일:** `frontend/app/(admin)/admin/gallery/page.tsx`

### Bug 1 — 페이지네이션 UI 추가
```tsx
// AdminPagination import 추가
import { AdminPagination } from '@/components/admin/AdminPagination'

// AdminSection 바로 아래에 조건부 렌더
{total > 12 && (
  <AdminPagination
    page={page}
    totalPages={Math.ceil(total / 12)}
    onPageChange={(p) => { setPage(p); setPreviewItem(null) }}
  />
)}
```
- `total > 12`일 때만 표시 (1페이지이면 페이지네이션 불필요)
- 페이지 변경 시 열려있는 모달도 닫기 (`setPreviewItem(null)`)

### Bug 2 — API 에러 핸들링 추가
```tsx
// 기존 (fire-and-forget)
onClick={() => { galleryApi.hdRender(item.post.id); toast.info('HD 렌더링 요청') }}

// 수정 후
onClick={() => galleryApi.hdRender(item.post.id)
  .then(() => toast.info('HD 렌더링 요청'))
  .catch(() => toast.error('HD 렌더 요청 실패'))}
```
- 카드 내 HD렌더/업로드 버튼, 모달 내 HD렌더/업로드 버튼 모두 수정 (총 4곳)

## 3. 테스트 결과물 저장 위치

프론트엔드 빌드: `frontend/.next/`

## 4. 수동 테스트 방법

```bash
cd frontend && npm run dev
# 또는
docker compose -f env/docker-compose.yml up -d --build frontend
```

1. `http://localhost:3000/admin/gallery` 접속
2. 12개 이상 렌더링된 영상이 있을 때 페이지네이션 버튼 확인 (없으면 표시 안 됨)
3. 다음 페이지 버튼 클릭 → 갤러리 목록 갱신 확인
4. HD렌더/업로드 버튼 클릭 시 에러 발생하면 에러 toast 표시 확인

## 5. 추천 commit message

```
fix: 갤러리 페이지네이션 UI 누락 + API 에러 핸들링 추가
```
