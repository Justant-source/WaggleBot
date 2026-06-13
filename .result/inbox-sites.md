# inbox-sites — 수신함 사이트 필터 동적화

## 1. 작업 결과

수신함 페이지의 사이트 필터 드롭다운이 `const SITE_CODES = [...]` 하드코딩에서
**백엔드 DB distinct 조회로 동적 로드**되도록 변경됐다.

인스티즈·더쿠·MLB파크 3개 신규 크롤러가 필터에 자동 반영된다.
이후 크롤러 추가 시 DB에 포스트가 수집되면 코드 변경 없이 드롭다운에 표시된다.

## 2. 수정 내용

| 파일 | 변경 내용 |
|------|----------|
| `backend/.../domain/PostRepository.java` | `findDistinctSiteCodes()` JPQL distinct 쿼리 추가 |
| `backend/.../controller/InboxController.java` | `GET /api/inbox/sites` 엔드포인트 추가 |
| `frontend/lib/api/inbox.ts` | `sites()` API 호출 추가 |
| `frontend/app/(admin)/admin/inbox/page.tsx` | `SITE_CODES` 상수 제거, `useState<string[]>([])` + 마운트 `useEffect` 추가, Select 드롭다운 동적 렌더링 |

## 3. 테스트 결과물 위치

```bash
curl http://localhost:8080/api/inbox/sites
# → ["bobaedream","dcinside","instiz","mlbpark","nate_pann","theqoo"]
```

DB에 수집된 6개 사이트 코드 알파벳 순 반환 확인 (fmkorea는 포스트 없음).

## 4. 수동 테스트 방법

1. 브라우저 `http://localhost:3000/admin/inbox` 접속
2. "전체 사이트" 드롭다운 클릭 → instiz·theqoo·mlbpark 포함한 사이트 목록 표시 확인
3. 각 사이트 선택 시 해당 사이트 포스트만 필터링되는지 확인

## 5. 추천 commit message

```
feat: 수신함 사이트 필터 동적화 (SITE_CODES 하드코딩 제거)

GET /api/inbox/sites → posts.site_code distinct 조회.
신규 크롤러(instiz·theqoo·mlbpark) 자동 반영.
```

## 6. DOC-MAP 기준 갱신한 문서 목록

없음 — CLAUDE.md "사이트 목록 하드코딩 금지" 규칙 이행이며 docs/ SSOT 범위 밖.
