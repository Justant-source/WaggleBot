# inbox-filter

## 1. 작업 결과

수신함 필터/검색 기능 추가 + settings TTS 목소리 드롭다운 교체.

| 항목 | 파일 |
|------|------|
| InboxController — siteCode/tier/q 필터 파라미터 추가 | `backend/.../InboxController.java` |
| inbox API 클라이언트 — 필터 파라미터 추가 | `frontend/lib/api/inbox.ts` |
| 수신함 페이지 — 사이트/티어 드롭다운 + 검색 UI | `frontend/app/(admin)/admin/inbox/page.tsx` |
| settings — TTS 목소리 텍스트 입력 → 드롭다운 교체 | `frontend/app/(admin)/admin/settings/page.tsx` |

## 2. 수정 내용

### 수신함 필터 (backend)
- `GET /api/inbox?siteCode=nate_pann&tier=tier1&q=키워드`
- JPA Criteria API로 동적 AND 조건 구성 (`siteCode`/`q`/`tier` 각각 null이면 조건 생략)
- `tier` 파라미터: tier1(≥80), tier2(30~79.99), tier3(<30) 점수 범위 필터
- `q` 파라미터: title like `%키워드%` (대소문자 무시)
- 티어 카운트를 `posts.getTotalElements()`에서 `postRepo.countByStatus(COLLECTED)` 전체 카운트로 수정 → 필터 적용해도 카운트가 틀리지 않음

### 수신함 필터 UI (frontend)
- 사이트 드롭다운: nate_pann / bobaedream / dcinside / fmkorea
- 티어 드롭다운: 전체 / 상위(≥80) / 중위(30~79) / 하위(<30)
- 검색 입력창: Enter 또는 돋보기 버튼으로 검색 실행
- "초기화" 버튼: 필터가 하나라도 활성화된 경우 표시
- 필터 변경 시 page=0, 선택 초기화 자동 실행

### TTS 목소리 드롭다운 (settings)
- 기존 자유입력 Input → Fish Speech 8개 목소리 Select 드롭다운으로 교체
- default/anna/han/krys/sunny/yohan/yura/manbo — config/settings.py의 TTS_VOICES와 동기화

## 3. 수동 테스트 방법

### 수신함 필터
```
1. /admin/inbox 접속
2. 사이트 드롭다운에서 "nate_pann" 선택 → nate_pann 게시글만 표시 확인
3. 티어 드롭다운에서 "상위(≥80)" 선택 → 높은 점수 게시글만 표시 확인
4. 검색창에 키워드 입력 → Enter 또는 검색 버튼 클릭
5. 초기화 버튼으로 전체 목록 복원 확인
```

### TTS 목소리
```
1. /admin/settings → TTS 섹션
2. 드롭다운에서 "Anna" 선택 → 저장
3. config/pipeline.json에 tts_voice=anna 저장 확인
```

## 4. 추천 commit message

```
feat: 수신함 사이트/티어/검색 필터 추가 + settings TTS 목소리 드롭다운 교체

- InboxController: siteCode/tier/q 필터 파라미터 + JPA Criteria 동적 쿼리
- 수신함 UI: 사이트 드롭다운, 티어 드롭다운, 제목 검색, 초기화 버튼
- 티어 카운트 버그 수정: 전체 카운트 기준으로 변경 (필터 시 틀리던 문제)
- settings TTS: 자유입력 → Fish Speech 목소리 프리셋 드롭다운
```
