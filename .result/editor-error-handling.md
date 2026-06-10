# editor-error-handling

## 1. 작업 결과

에디터 상세 페이지 (`editor/[postId]/page.tsx`)에서 API 에러 핸들링 누락 버그 4개 수정.

- **Bug**: `handleSave`, `handleGenerate`, `handleTtsPreview`, `handleConfirm` 핸들러에 try/catch 없음
  → API 호출 실패 시 후속 상태 업데이트(`markClean`, `setGenerateJobId`, `setTtsJobId`) 미실행 + 에러 toast 없음

## 2. 수정 내용

**파일:** `frontend/app/(admin)/admin/editor/[postId]/page.tsx`

```tsx
// 기존 — handleSave, handleGenerate, handleTtsPreview, handleConfirm 모두 try/catch 없음
const handleSave = async () => {
  if (!script) return
  await editorApi.saveScript(id, script)  // 실패 시 이후 코드 스킵, 피드백 없음
  markClean(); toast.success('저장됨')
}

// 수정 후
const handleSave = async () => {
  if (!script) return
  try {
    await editorApi.saveScript(id, script)
    markClean(); toast.success('저장됨')
  } catch { toast.error('저장 실패') }
}
```

수정 대상: `handleSave`, `handleGenerate`, `handleTtsPreview`, `handleConfirm` (4개 핸들러)

## 3. 테스트 결과물 저장 위치

프론트엔드 빌드: `frontend/.next/`

## 4. 수동 테스트 방법

```bash
cd frontend && npm run dev
```

1. `http://localhost:3000/admin/editor/{id}` 접속
2. 백엔드 종료 상태에서 "저장" 버튼 클릭 → `toast.error('저장 실패')` 확인
3. "대본 생성" 클릭 → `toast.error('대본 생성 요청 실패')` 확인
4. "TTS 미리듣기" → `toast.error('TTS 미리듣기 요청 실패')` 확인
5. "확정" → `toast.error('확정 실패')` 확인

## 5. 추천 commit message

```
fix: 에디터 상세 페이지 API 에러 핸들링 추가
```

## 6. DOC-MAP 기준 갱신한 문서 목록

없음
