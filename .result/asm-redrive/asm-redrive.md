# asm-redrive

## 1. 작업 결과

telegram-bridge가 ASM(Again-Spring-Marketing) `redrive:`/`ignore:` 콜백을
**필드 개수를 해석하지 않고 그대로** ASM에 전달하도록 검증/확인 완료.
callback_data가 4-field → 5-field(`asmJobUlid` 추가)로 바뀌어도 브리지 코드
변경이 필요 없음을 확인했고, 관련 env var·문서를 코드에 맞춰 갱신했다.
빌드(`tsc --noEmit`) 클린, 커밋 2건 생성, **push는 하지 않았고 컨테이너
재빌드/재시작도 하지 않았다.**

## 2. Before / After — 콜백 처리 경로

**Before(오늘 이전 커밋 기준):** `handleCallback`은 모든 `callback_query`에
대해 곧바로 `bot.answerCallbackQuery(query.id)`를 호출한 뒤 `data.split(":")`
결과로 스위치 분기했다. `redrive:`/`ignore:` 전용 분기가 없어 `default:
Unknown callback` 브랜치로 떨어져 조용히 버려졌을 것이고, 브리지가 먼저
답변해버려 ASM이 나중에 같은 콜백에 답하면 Telegram이 거부(콜백당 1회 응답
제한)했을 것이다.

**After(오늘 오전 이미 uncommitted 상태로 작성되어 있던 코드, 이번에 검증):**
`handleCallback` 맨 앞에서 `[prefix, ...rest] = data.split(":")`로 prefix만
뽑아 `prefix === "redrive" || prefix === "ignore"`면 즉시
`forwardMarketingCallback(query.id, data)`를 호출하고 `return` — **raw
`data` 문자열 전체**를 파싱 없이 ASM URL로 POST한다. 그 아래
`bot.answerCallbackQuery(query.id)` 일괄 호출부와 스위치문은 redrive/ignore
분기 이후에 위치해 있어 도달하지 않는다(`return` 때문). ASM 실패 시에만
브리지가 폴백으로 `answerCallbackQuery`를 호출한다.

**결론:** 요청한 "5-field 허용" 변경은 **코드 수정 없이 이미 만족**되어
있었다 — `prefix` 매칭과 raw string 포워딩만 하고 `rest`/필드 수/정규식
검증을 전혀 하지 않기 때문. 4-field든 5-field든 동일하게 통과한다. 코드를
추가로 건드리지 않았다(요청사항이 "prefix 매치 이상의 검증 추가 금지"였으므로
이 상태가 정답).

## 3. 확인 사항 — blanket answerCallbackQuery

- `handleCallback`의 무조건 `answerCallbackQuery` 호출은 redrive/ignore 분기
  **뒤**에 있고, 그 분기는 앞에서 `return`하므로 **충돌 없음**을 확인.
- `TelegramBotWrapper.withCallbackAuth`(`telegram/src/bot/telegram-bot.ts:40`)는
  (a) 미인가 사용자면 자체적으로 `answerCallbackQuery`(⛔ 메시지) 후 handler를
  아예 호출하지 않음 — redrive/ignore 버튼도 `ALLOWED_USER_IDS`에 있는
  사용자만 클릭 가능해야 정상 동작(범위 밖이라 별도 조치 안 함).
  (b) handler(`handleCallback`)가 throw하면 catch에서 `answerCallbackQuery`
  (❌ 오류 발생)를 호출 — 하지만 `forwardMarketingCallback`은 fetch
  실패/타임아웃/non-2xx를 모두 자체 try/catch로 흡수하고 절대 rethrow하지
  않으므로 이 catch 경로는 redrive/ignore에 대해 실행되지 않음. 즉 ASM 쪽
  응답과 경합할 여지가 없다.
- 결론: **ASM이 answer를 온전히 소유**하며, 브리지는 ASM 연결 자체가 실패한
  경우에만 폴백 answer를 보낸다 — 요청한 설계 그대로 이미 구현되어 있었다.

## 4. 수정 내용

### 코드 (기존 uncommitted 작업 검증만, 변경 없음)
- `telegram/src/bot/command-handler.ts` — redrive/ignore forwarder (기존 작성분 확인)
- `telegram/src/config.ts` — `config.asm.{callbackUrl,bearerToken}` (기존 작성분 확인)

### 이번에 추가 수정 (Doc-Sync 게이트 대응)
- `env/docker-compose.yml`(기존 diff, uncommitted) — `ASM_TELEGRAM_CALLBACK_URL`, `ASM_BEARER_TOKEN` env var 추가 확인
- `env/.env.example` — 위 두 env var 추가 (신규 반영, 이전에 누락돼 있었음)
- `docs/20-containers/topology.md` — telegram-bridge 섹션에 ASM env var 2종 + forwarder 설명 추가, `last-verified` 2026-08-20 갱신
- `docs/20-containers/config.md` — "Telegram → ASM 마케팅 콜백 forwarder" 표 신규 추가, `last-verified` 2026-08-20 갱신
- `python3 scripts/lint_docs.py` — 6개 검사 전부 PASS

### drive-by 빌드 픽스 (요청대로 유지)
- `telegram/src/pipeline/pipeline-commands.ts:36` — `(status as Record<string, number>)` → `(status as unknown as Record<string, number>)`. redrive 작업과 무관, `tsc` 빌드 차단 해소용.

### 커밋 범위 밖으로 남긴 것
- `worker/ai_worker/{core/processor.py, renderer/_frames.py, renderer/layout.py, scene/again_spring_text.py, scene/director.py}`, `worker/test/test_again_spring_text.py` — 여전히 uncommitted. 최근 커밋 이력(`fix(marketing): ...`)과 같은 계열의 **별개 진행 중 작업**으로 판단, 이번 telegram-bridge 태스크 범위 밖이라 손대지 않고 그대로 두었음. 별도 커밋 필요 시 알려달라.

## 5. 테스트 결과물 위치

- `tsc --noEmit` 실행 로그: 본 결과물 파일에 요약(아래 4번 항목), 별도 파일 생성 없음(콘솔 출력이 비어있어 클린 = 통과)
- `python3 scripts/lint_docs.py` 실행 결과: PASS (6/6) — 본 문서 3번 항목에 요약
- 자동화 테스트 없음 — `telegram/` 패키지에 `*.test.ts`/`*.spec.ts` 파일 자체가 존재하지 않음(확인 완료, 실행할 테스트가 없음)

## 6. 수동 테스트 방법

이 태스크는 "NO rebuilds, NO restarts" 조건이라 컨테이너 재기동 없이 코드
정적 검증만 수행했다. 실제 동작 확인은 배포자가 재배포 후 다음을 확인:

```bash
# 1. telegram-bridge 재빌드/재시작은 오퍼레이터가 수행
docker compose -f env/docker-compose.yml up -d --build telegram-bridge

# 2. ASM이 4-field 레거시 콜백에 명시적으로 REFUSE하는지 확인
#    (오래된 채팅 기록의 구버전 버튼 클릭 시나리오)

# 3. ASM이 신규 5-field 콜백을 정상 처리하는지 확인
#    (새로 발송되는 알림의 redrive/ignore 버튼)

# 4. 두 경우 모두 telegram-bridge 로그에서 파싱/검증 에러 없이
#    forwardMarketingCallback 호출만 찍히는지 확인:
docker compose -f env/docker-compose.yml logs --tail 50 telegram-bridge
```

## 7. 추천 commit message

이미 아래 두 커밋으로 분리 생성 완료(추가 커밋 불필요):

```
9c6d640 feat(telegram): forward ASM marketing redrive/ignore callbacks verbatim
11862da fix(telegram): unblock build on getPipelineStatus() cast
```

## 8. Doc-Sync

`docs/20-containers/topology.md`, `docs/20-containers/config.md` 갱신 완료
(env var 추가에 대응, 트리거 맵 규칙: `env/docker-compose.yml` → 두 문서).
`python3 scripts/lint_docs.py` PASS. **push는 수행하지 않음** — 자격 증명
필요 여부와 무관하게 요청 범위가 커밋까지였음.
