# dashboard-overhaul

## 1. 작업 결과

대시보드 4개 에픽 전체 구현 완료 (수신함 옥석판별 · 에디터 TTS/프롬프트 · 파이프라인 진행상황 · 오버뷰 홈).

신규 컴포넌트 9개, 페이지 1개 생성, 기존 페이지 4개 수정, 신규 Python/Java/Config 파일 다수.

## 2. 수정/생성 내용

### 신규 컴포넌트

| 파일 | 역할 |
|------|------|
| `components/inbox/AiFitnessBadge.tsx` | AI 점수 pill (≥70 녹색/40-69 호박/미만 회색) + 미분석 버튼 + Star 아이콘 |
| `components/inbox/ScoreBreakdown.tsx` | 점수 구성 클릭팝업 (조회×0.1, 추천×2.0, 댓글×1.5, 시간감쇠) |
| `components/inbox/CommentList.tsx` | 베스트 댓글 목록, 마운트 시 `inboxApi.comments()` 호출, 로딩 스켈레톤 |
| `components/inbox/TriageDrawer.tsx` | DetailDrawer 대체, AI 이유 amber박스, 이전/다음 화살표, 단축키 힌트 |
| `components/editor/VoicePicker.tsx` | 4×2 그리드, 샘플 재생/정지, 전역기본값 카드, ring 선택효과 |
| `components/editor/PromptPresetPanel.tsx` | 6개 프리셋 칩, textarea 글자수 카운터, AI 대본 재생성 버튼 |
| `components/editor/MoodGrid.tsx` | 3×3 9종 무드 그리드, primary/muted 선택 시각화 |
| `components/progress/PhaseStepper.tsx` | 8단계 완료/현재/미래 시각화, pulsing ring, 취소선 skip |
| `components/progress/ProcessingCard.tsx` | PhaseStepper + Phase7 씬 진행바 + 경과시간(1초틱) + 응답없음 배지 |

### 수정된 페이지

**`app/(admin)/admin/inbox/page.tsx`**
- `detail` → `detailIdx` 인덱스 기반으로 전환
- 낙관적 승인/거절 (목록에서 즉시 제거, 실패 시 재조회)
- 키보드 신속심사: J/K/ArrowDown/ArrowUp 이동, A/Enter 승인, D 거절, Esc 닫기
- IME 가드, 입력요소 포커스 가드, meta/ctrl/alt 가드
- 드로어 열릴 때 `activeElement.blur()`, 행 `scrollIntoView` + `aria-selected` ring 하이라이트
- 정렬 Select (점수순/AI점수순/최신순), "오늘 수집" 토글칩, "★ 추천만" 토글칩
- "미분석 일괄 분석" 버튼, "일괄 거절" 버튼 추가
- AI 점수 컬럼 (`AiFitnessBadge`), 점수 셀 (`ScoreBreakdown`)
- `PostDetailDrawer` → `TriageDrawer` 교체

**`app/(admin)/admin/editor/[postId]/page.tsx`**
- `ttsVoice`, `genInstructions`, `variantGroup`, `variantLabel` 상태 추가
- 무드 Select → `MoodGrid` 교체
- "AI 대본 생성" 버튼 → `PromptPresetPanel` 교체
- TTS 미리듣기 영역에 `VoicePicker` 삽입
- `editorApi.setVoice()` 연동 + toast
- A/B 배지 (variantGroup 있을 때 제목 옆)
- 줄별 글자수 카운터 (maxCharsPerLine 초과 시 빨간 텍스트)

**`app/(admin)/admin/progress/page.tsx`**
- 처리 중 목록 div → `ProcessingCard` 교체
- 처리 중 항목 있으면 5s, 없으면 10s 폴링 (동적 interval)
- 응답없음 경고 로직 ProcessingCard로 이전

**`app/(admin)/admin/gallery/page.tsx`**
- `GalleryItem.content` 타입에 `ttsVoice`, `variantLabel` 추가
- 카드 배지 행에 회색 🎙 보이스 배지, 파란 A/B 배지 추가

### 신규 페이지

**`app/(admin)/admin/overview/page.tsx`**
- KPI 4개 (오늘 수집/업로드, 처리대기, 실패)
- 상태별 수평 퍼널 바 차트
- 처리 중 목록 (최대 3개, 더 있으면 "진행상황 보기" 링크)
- 최근 업로드 성과 테이블 (제목/조회/좋아요)
- 수신함/편집실/실패건 바로가기 버튼
- 30초 자동 폴링

## 3. 테스트 결과물 저장 위치

없음 (UI 컴포넌트)

## 4. 수동 테스트 방법

```bash
# 프론트엔드 실행
cd frontend && npm run dev

# 테스트 항목
1. /admin/overview — KPI 카드, 퍼널 바, 처리중/성과 테이블, 바로가기 버튼
2. /admin/inbox — J/K 키보드 이동, A승인/D거절, AiFitnessBadge "미분석" 클릭, ScoreBreakdown 클릭팝업, 정렬/오늘수집/추천만 필터
3. /admin/editor/{id} — VoicePicker 보이스 선택, PromptPresetPanel 프리셋 칩, MoodGrid 9종 선택, 줄별 글자수 카운터
4. /admin/progress — ProcessingCard PhaseStepper, 씬 진행바, 경과시간 틱
5. /admin/gallery — 카드 배지 영역에 🎙 보이스, A/B 라벨 표시
```

## 5. 추천 commit message

```
feat: 대시보드 대개편 — inbox 키보드 심사/AI배지, editor 보이스/프리셋/무드그리드, progress PhaseStepper, gallery 배지, overview 신규
```
