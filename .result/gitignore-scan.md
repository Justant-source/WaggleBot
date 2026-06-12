# gitignore 보완 + implementation-status 동기화

## 1. 작업 결과

- `.gitignore`에 누락된 경로 5개 추가
- `docs/implementation-status.md` last-verified 갱신 + 다크모드·VRAM 모니터링·pytest픽스 기록 추가

## 2. 수정 내용

### `.gitignore`

```
# 신규 추가
worker/test/test_image_filter_output
worker/test/test_prompt_engine_output
worker/test/test_video_rendering_output
worker/media/
.claude/config.json
.claude/*.lock
```

- 이전 항목(`test_layout_output` 등)에는 있으나 최근 신규 테스트 모듈이 생성한 디렉터리 3개 누락
- `worker/media/` — 런타임 생성 음성·영상 임시파일 디렉터리
- `.claude/config.json`, `.claude/*.lock` — Claude Code 자체 런타임 파일 (프로젝트 설정 아님)

### `docs/implementation-status.md`

- `last-verified`: `2026-06-11 (3ba0d15)` → `2026-06-12 (656dffd)`
- "장기 개선 후보 미구현" 테이블에서 "VRAM 누수 모니터링"·"대시보드 다크모드" 제거 (구현 완료)
- 신규 섹션 "다크모드 + pytest 컬렉션 픽스 (2026-06-12)" 추가

## 3. 테스트 결과물 위치

없음 (문서·설정 변경)

## 4. 수동 테스트 방법

```bash
git status --short   # 추적 외 디렉터리 목록에서 worker/media 등이 사라졌는지 확인
```

## 5. 추천 commit message

```
chore: .gitignore 보완(test-output·media·claude-runtime) + implementation-status 동기화
```

## 6. DOC-MAP 기준 갱신한 문서 목록

- `docs/implementation-status.md` — last-verified 갱신, 다크모드/VRAM/pytest 구현 기록 추가
