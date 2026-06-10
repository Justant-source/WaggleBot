# editor-body

## 1. 작업 결과

에디터 페이지 body 항목 편집 기능 추가 (이전에는 hook/closer/mood만 편집 가능).

| 항목 | 파일 |
|------|------|
| 에디터 body 항목 편집 UI | `frontend/app/(admin)/admin/editor/[postId]/page.tsx` |

## 2. 수정 내용

### 에디터 body 편집
- hook/closer 사이에 body 항목 섹션 추가
- 각 ScriptBodyItem을 카드로 표시:
  - `type=body` → 파란 배지 "본문 N"
  - `type=comment` → 보라 배지 "댓글 (·author)"
- `item.lines.join('\n')`으로 textarea에 표시
- 수정 시 `\n` 분리하여 lines 배열 재구성, `lineCount` 업데이트
- `updateField('body', newBody)` → `dirty=true` 자동 설정

## 3. 수동 테스트 방법

```
1. /admin/editor 접속 → 편집 가능한 게시글 선택
2. body 섹션에 각 항목이 카드로 표시되는지 확인
3. 텍스트 수정 후 저장 버튼 활성화 확인
4. 저장 → 에디터 재진입 시 수정 내용 유지 확인
```

## 4. 추천 commit message

```
feat: 에디터 body 항목 편집 기능 추가 (본문/댓글 인라인 수정)
```
