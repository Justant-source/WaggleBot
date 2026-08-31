# marketing-sla

## 1. 작업 결과

Again Spring 외부 마케팅 잡의 우선 처리, LLM/GPU 락 분리, 고속 대본 경로, 10분 SLA 품질 축소와 진행 상태 응답을 구현했다.

## 2. 수정 내용

- `source=again_spring`을 critical 우선순위로 저장하고 APPROVED 선택/렌더 대기열을 우선순위화했다.
- 외부 API에 `priority`, `deadlineAt`, `preScripted`, `renderProfile`을 추가했다. critical 잡의 deadline 기본값은 ingest 후 10분이다.
- 원격 Claude 대본 생성은 GPU 락 밖에서 실행하고 Fish Speech만 GPU 락을 사용한다.
- `preScripted=true` Again Spring 잡은 결정적 로컬 분할로 LLM을 건너뛴다.
- deadline을 지난 잡은 실패하지 않고 댓글을 1건으로 축소하며 `degraded` 상태를 응답한다.
- 댓글 보이스/음성 캐시를 작성자·voice·text·emotion 기반으로 결정화해 플랫폼 간 재사용한다.
- progress에 `lastHeartbeatAt`을 넣고 TTS 중 30초마다 갱신한다.

## 3. 테스트 결과물 위치

- focused test: `worker/test/test_marketing_runtime.py`
- `python3 -m compileall` 통과
- `backend/gradlew test --no-daemon` 통과 (프로젝트에 Java test source 없음)
- `python3 scripts/lint_docs.py` 통과
- Python pytest는 현재 호스트에 `sqlalchemy`가 설치돼 있지 않아 수집 단계에서 실행 불가였다.

## 4. 수동 테스트 방법

1. `POST /api/external/jobs`에 `source=again_spring`, `preScripted=true`로 요청한다.
2. GET 응답에서 `priority=MARKETING_CRITICAL`, `deadlineAt`, `progress.lastHeartbeatAt`을 확인한다.
3. deadline을 과거로 둔 잡을 렌더하면 `degraded=true`와 `degradeReasons`가 나오고 댓글 1건만 낭독되는지 확인한다.

## 5. 추천 commit message

`feat(wagglebot): prioritize critical marketing renders and expose SLA progress`

## 6. Doc-Sync

- `docs/30-components/pipeline.md`
- `docs/50-api/rest-spec.md`
- `docs/60-runtime/pipeline-runtime.md`
