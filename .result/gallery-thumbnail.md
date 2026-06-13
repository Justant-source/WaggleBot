# gallery-thumbnail — 갤러리 카드 YouTube 썸네일 표시

## 1. 작업 결과

갤러리 카드 프리뷰가 기존 `<video preload="metadata">` (첫 프레임 로딩 느림) 대신
**생성된 YouTube 썸네일 JPG**를 우선 표시하도록 변경됐다.

- `content.uploadMeta.thumbnail_path` 있을 때: 16:9 `<img>` (빠른 로딩, 실제 YouTube 노출 이미지)
- 없을 때: 기존 video 폴백 유지
- 풀스크린 모달: 9:16 비디오 옆에 "YouTube 썸네일" 미리보기 패널(w-56) 추가

## 2. 수정 내용

| 파일 | 변경 내용 |
|------|----------|
| `frontend/app/(admin)/admin/gallery/page.tsx` | `GalleryItem.content` 타입에 `uploadMeta` 추가, `getMediaUrl()`+`getThumbnailUrl()` 헬퍼 신규, 카드 프리뷰 → 썸네일 우선 로직, 모달 → 썸네일 사이드 패널 추가 |

## 3. 테스트 결과물 위치

프론트엔드 재빌드 완료 (`docker compose up -d --build frontend`).
브라우저 `http://localhost:3000/admin/gallery` — 썸네일이 생성된 포스트 카드에서 16:9 JPG 표시 확인.

## 4. 수동 테스트 방법

1. PREVIEW_RENDERED 이상 포스트가 있고 해당 포스트에 `thumbnail_path`가 있을 때:
   - 갤러리 카드 프리뷰가 16:9 황색 헤더 와글 썸네일 이미지로 표시되는지 확인
   - 카드 클릭 → 모달에서 비디오 재생 + 우측 썸네일 패널 확인
2. `thumbnail_path` 없는 포스트:
   - 기존처럼 `<video>` 첫 프레임 표시 (폴백 동작 확인)

## 5. 추천 commit message

```
feat: 갤러리 카드 YouTube 썸네일 표시 + 모달 썸네일 패널

uploadMeta.thumbnail_path → 카드 <img>(16:9) 우선 / video 폴백.
풀스크린 모달에 썸네일 사이드 패널(w-56) 추가.
```

## 6. DOC-MAP 기준 갱신한 문서 목록

없음 — 프론트엔드 UI 개선으로 docs/ SSOT 범위 밖.
