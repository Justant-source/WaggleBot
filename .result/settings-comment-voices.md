# settings-comment-voices — 댓글 화자 음성 후보 설정 UI 추가

## 1. 작업 결과

설정 페이지 TTS 섹션에 **댓글 화자 음성 후보(comment_voices) 체크박스 그리드**가 추가됐다.
기존에는 `pipeline.json`을 직접 편집해야 했던 `comment_voices` 배열을
어드민 UI에서 24개 음성 중 체크박스로 선택·저장할 수 있다.

- 내레이터 기본 음성(기존 Select 드롭다운) 바로 아래에 위치
- 3컬럼 체크박스 그리드, 선택된 음성은 primary 색상 강조
- 하단에 "선택됨: manbo, anna, ..." 요약 텍스트 표시
- 저장 시 `comment_voices: string[]` 배열로 pipeline.json에 반영

## 2. 수정 내용

| 파일 | 변경 내용 |
|------|----------|
| `frontend/app/(admin)/admin/settings/page.tsx` | `commentVoices` 상태 추가, `useEffect` 로드 배선, `onSubmit` 페이로드에 포함, TTS 섹션에 체크박스 그리드 추가 |

## 3. 테스트 결과물 위치

브라우저 `http://localhost:3000/admin/settings` → TTS 섹션 → 댓글 화자 음성 후보 체크박스 표시 확인.
현재 4개(manbo·anna·han·yura)가 체크된 상태로 로드됨.

## 4. 수동 테스트 방법

1. `/admin/settings` 접속 → TTS 섹션 확인
2. 체크박스를 체크/해제 후 저장 버튼 클릭
3. 페이지 새로고침 후 선택 상태 유지 확인
4. 컨테이너에서 `cat /app/config/pipeline.json | python3 -c "import sys,json; d=json.load(sys.stdin); print('comment_voices:', d.get('comment_voices'))"` 로 실제 반영 확인

## 5. 추천 commit message

```
feat: 설정 UI에 댓글 화자 음성 후보(comment_voices) 체크박스 추가

다화자 TTS의 댓글 씬 화자 배정 음성을 UI에서 편집 가능.
24개 음성 체크박스 그리드, pipeline.json comment_voices 배열로 저장.
```

## 6. DOC-MAP 기준 갱신한 문서 목록

없음 — 설정 UI 개선으로 docs/ SSOT 범위 밖.
