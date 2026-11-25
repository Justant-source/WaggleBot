# 프로젝트 경로 재정리 (docs/설정 업데이트)

## 1. 작업 결과

`llm-worker/` → `worker/llm/`, `claude-telegram-bridge/` → `telegram/` 디렉터리 이름 변경에 따른
문서 및 설정 파일 경로 참조를 최소한으로 업데이트 완료.

## 2. 수정 내용

### 변경된 파일

| 파일 | 변경 내용 |
|------|-----------|
| `.claude/settings.json` | Stop 훅 스크립트 경로: `claude-telegram-bridge/scripts/stop-notify.mjs` → `telegram/scripts/stop-notify.mjs` |

### 변경 없는 파일

| 파일 | 사유 |
|------|------|
| `CLAUDE.md` | 이미 `worker/` 하위 경로를 사용 중. `llm-worker/` 폴더 경로 참조 없음. `claude-telegram-bridge/` 참조 없음. Docker 서비스명 `llm-worker`는 유지 대상이므로 변경 불필요. |
| `README.md` | 프로젝트 트리가 이미 `worker/` 구조로 작성됨. `claude-telegram-bridge/` 또는 루트 `llm-worker/` 항목 없음. |

## 3. 테스트 결과물 저장 위치

해당 없음 (설정 파일 경로 수정만).

## 4. 수동 테스트 방법

Claude Code 세션 종료 시 Stop 훅이 정상 실행되는지 확인:

```bash
# telegram/scripts/stop-notify.mjs 파일 존재 확인
ls /home/justant/Data/WaggleBot/telegram/scripts/stop-notify.mjs

# 훅 명령어 직접 실행 테스트
node /home/justant/Data/WaggleBot/telegram/scripts/stop-notify.mjs
```

## 5. 추천 commit message

```
chore: claude-telegram-bridge → telegram 경로 변경 반영 (.claude/settings.json)
```
