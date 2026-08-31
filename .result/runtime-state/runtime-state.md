# Runtime-state isolation

## 1. 작업 결과

- `contents.pipeline_state`의 공유 JSON 갱신을 `content_runtime_state`의 키별 원자적 upsert로 분리했다.
- pre-scripted Again Spring 영상은 좋아요 상위 댓글 2개(동률 댓글 ID 순)만 렌더하며, 본문 narrator 길이와 댓글/아웃트로 tail 길이를 별도 진단으로 남긴다.
- 외부 잡 폴링 응답은 실패 시 구조화된 failure code/stage/retryable/error summary를 제공한다.

## 2. 수정 내용

- migration `009_content_runtime_state.sql`, Python runtime state helper, progress/checkpoint/SLA/failure/diagnostic 저장 경로.
- Java external GET 응답의 새 runtime state 조회 및 하위 호환 legacy fallback.
- 마케팅 댓글 2개 정책과 길이 진단.

## 3. 테스트 결과물 위치

- `worker/test/test_runtime_state_policy.py` — 런타임 namespace 및 댓글 정책 회귀 테스트.
- `python3 -m py_compile ...` 통과.
- `./backend/gradlew -p backend compileJava` 통과.
- `python3 scripts/lint_docs.py` 통과.
- 로컬 Python 환경에 SQLAlchemy가 없어 pytest collection은 실행 불가였다. 컨테이너/의존성 설치 환경에서 `PYTHONPATH=worker pytest -q worker/test/test_runtime_state_policy.py worker/test/test_marketing_runtime.py`를 실행한다.

## 4. 수동 테스트 방법

1. migration runner로 009 적용 후 동일 content의 progress/checkpoint/SLA를 병렬 갱신한다.
2. `GET /api/external/jobs/{id}`에서 `progress`, `generationDiagnostics`와 FAILED의 failure envelope을 확인한다.
3. pre-scripted Again Spring 사연을 렌더해 댓글 2개와 길이 진단을 확인한다.

## 5. 추천 commit message

`fix(marketing): isolate runtime state and expose render diagnostics`

## 6. Doc-Sync

- `docs/40-data/schema.md`
- `docs/50-api/rest-spec.md`
- `docs/60-runtime/pipeline-runtime.md`
