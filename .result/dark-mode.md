# dark-mode

## 1. 작업 결과

다크모드 토글 버튼(`AdminTopBar`의 Moon/Sun 버튼)이 실제로 동작하도록 연결.
기존: `ThemeProvider` 없어 `useTheme()`가 theme="light" 고정 → 토글해도 아무 변화 없음.
이후: 토글 시 `<html>` 에 `dark` 클래스 추가/제거 → 셸 전체(사이드바·상단바·메인 배경)가 다크 모드로 전환.

## 2. 수정 내용

### `frontend/app/providers.tsx` (신규)
- `ThemeProvider` 클라이언트 컴포넌트 래퍼 — `attribute="class"`, `defaultTheme="light"`, `enableSystem=false`

### `frontend/app/layout.tsx`
- `Providers` import + `<body>` 자식을 `<Providers>`로 감쌈 (서버 컴포넌트에서 직접 ThemeProvider 사용 불가 → 클라이언트 래퍼 경유)

### `frontend/components/admin/shell/AdminTopBar.tsx`
- `bg-white` → `bg-background`, `border-gray-200` → `border-border`
- `text-gray-500 hover:bg-gray-100` → `text-muted-foreground hover:bg-accent` (× 2버튼)
- `text-gray-800` → `text-foreground`

### `frontend/components/admin/shell/AdminSidebar.tsx`
- 사이드바 컨테이너: `bg-white border-gray-200` → `bg-background border-border`
- 접기 버튼: `border-gray-200 bg-white hover:bg-gray-50` → `border-border bg-background hover:bg-accent`
- 화살표 아이콘: `text-gray-500` → `text-muted-foreground`
- 로고 영역: `border-gray-200` → `border-border`, `text-gray-900` → `text-foreground`
- 그룹 라벨: `text-gray-400` → `text-muted-foreground`
- 비활성 nav 항목: `text-gray-600 hover:bg-gray-100 hover:text-gray-900` → `text-muted-foreground hover:bg-accent hover:text-accent-foreground`
- 활성 nav 항목: `bg-blue-50 text-blue-700` + dark 변형 `dark:bg-blue-900/30 dark:text-blue-300`
- 활성 아이콘: `text-blue-600` + `dark:text-blue-400`, 비활성: `text-gray-500` → `text-muted-foreground`

### `frontend/components/admin/shell/AdminShell.tsx`
- 메인 콘텐츠 배경: `bg-gray-50` → `bg-muted/40`

## 3. 테스트 결과물 위치

프론트엔드 변경으로 자동 테스트 없음. `frontend/app/providers.tsx` 신규 파일.

## 4. 수동 테스트 방법

```bash
# 프론트엔드 컨테이너에서 (또는 로컬 npm run dev)
docker compose -f env/docker-compose.yml up frontend
# 브라우저에서 /admin 접속 → 우측 상단 Moon 버튼 클릭
# 확인: 사이드바(배경·텍스트·구분선), 상단바, 메인 배경이 다크 테마로 전환되는지
# Sun 버튼 클릭 → 라이트 모드 복원 확인
# 새로고침 후에도 테마가 유지되는지 확인 (ThemeProvider가 localStorage 사용)
```

shadcn/ui 기반 컴포넌트(카드, 테이블, 버튼 등)는 CSS 변수를 사용하므로 콘텐츠 페이지도 자동으로 다크 모드에 반응한다. 하드코딩된 `text-gray-*` / `bg-gray-*`가 남은 콘텐츠 컴포넌트는 별도 개선 여지가 있다.

## 5. 추천 commit message

```
feat: 다크모드 활성화 — ThemeProvider 연결 + 셸 컴포넌트 CSS 변수화
```

## 6. DOC-MAP 기준 갱신한 문서 목록

없음 (UI 기능 추가, docs 기술 범위 밖)
