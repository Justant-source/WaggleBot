# WaggleBot — AI Agent 개발 플레이북

> last-verified: 2026-08-31 · code-ref: `AGENTS.md`, `CLAUDE.md`, `docs/_index.md`, 코드 전역
> scope: AI agent가 코드 변경을 시작하기 전 읽는 작업 절차, 탐색 경로, 검증 기준

이 문서는 구현 세부의 정본이 아니다. 상세 사실은 작업 유형별 문서와 코드가 정본이며,
충돌 시 우선순위는 `runtime code > docs/_index.md > 하위 docs > README.md`이다.

## 작업 시작 순서

1. 루트 `AGENTS.md` 또는 `CLAUDE.md`를 읽어 불변 규칙과 문서 라우팅을 확인한다.
2. `docs/_index.md`의 트리거 맵에서 작업 영역에 대응하는 SSOT 문서를 찾는다.
3. 해당 문서를 먼저 읽고, 그 다음 코드 진입점을 `rg`로 확인한다.
4. 코드 변경 전에는 문서와 코드가 충돌하는 지점을 메모한다. 충돌하면 코드가 우선이다.
5. 코드 변경 후에는 같은 커밋 범위에서 대응 문서와 `README.md`를 실제 코드 상태로 맞춘다.
6. 완료 전 `python3 scripts/lint_docs.py`를 실행하고, `.result/{작업명}/{작업명}.md`를 작성한다.

## 하위 시스템 진입점

| 작업 | 먼저 볼 문서 | 코드 진입점 |
|------|--------------|-------------|
| 전체 구조·외부 경계 | `docs/10-context/system-context.md` | `env/docker-compose.yml`, `README.md` |
| 컨테이너·포트·볼륨·GPU | `docs/20-containers/topology.md` | `env/docker-compose.yml` |
| 설정·환경변수 | `docs/20-containers/config.md` | `config/settings.py`, `config/pipeline.json` |
| AI 파이프라인 | `docs/30-components/pipeline.md` | `worker/ai_worker/pipeline/content_processor.py` |
| 런타임 루프·재시도 | `docs/60-runtime/pipeline-runtime.md` | `worker/ai_worker/core/processor.py`, `worker/ai_worker/core/main.py` |
| DB·상태·Job | `docs/40-data/schema.md`, `docs/60-runtime/post-state-machine.md` | `worker/db/models.py`, `backend/src/main/resources/db/migration/` |
| REST API | `docs/50-api/rest-spec.md`, `docs/50-api/flows.md` | `backend/src/main/java/com/wagglebot/controller/`, `worker/llm/src/main/java/` |
| 크롤러 | `worker/crawlers/ADDING_CRAWLER.md` | `worker/crawlers/`, `worker/crawlers/plugin_manager.py` |
| 업로더 | `worker/uploaders/ADDING_UPLOADER.md` | `worker/uploaders/`, `scripts/youtube_auth.py`, `scripts/tiktok_auth.py` |
| 프론트엔드 | `docs/30-components/implementation-status.md` | `frontend/app/(admin)/admin/`, `frontend/lib/api/` |

## 불변 규칙 체크리스트

- 모든 LLM 호출은 `worker/ai_worker/llm/transport.py`의 `call_llm()` 또는 `call_llm_raw()`를 경유한다.
- 신규 LLM HTTP 호출, Ollama, qwen2.5, 로컬 LLM 경로를 추가하지 않는다.
- GPU 작업은 `gpu_manager.managed_inference(...)` 컨텍스트와 단계 후 캐시 해제를 유지한다.
- FFmpeg 최종 렌더링은 `h264_nvenc` 단일 `filter_complex` 패스를 유지한다.
- ComfyUI는 `--lowvram --reserve-vram 2`를 유지하고 `--normalvram`으로 바꾸지 않는다.
- LTX-2 프레임 수는 `1+8k`, 해상도는 8의 배수 검증 함수를 통과해야 한다.
- DB 세션은 `with SessionLocal() as db:` 패턴을 사용한다.
- 설정은 `config/` 경유로 읽고, 로직 안에 신규 `os.getenv()`를 흩뿌리지 않는다.
- 크롤러 사이트 목록은 `CrawlerRegistry.list_crawlers()`로 동적 조회한다.
- `ai_worker/video`에서 `ai_worker/tts`를 import하지 않는다.

## 검증 매트릭스

| 변경 영역 | 기본 검증 |
|-----------|-----------|
| 문서만 변경 | `python3 scripts/lint_docs.py` |
| Python worker | `cd worker && python -m pytest` 또는 관련 `python -m pytest test/<파일>.py` |
| LLM/파이프라인 | 관련 unit test + `worker/ai_worker/llm/transport.py` call_type 라우팅 확인 |
| backend | `cd backend && ./gradlew test` 또는 최소 `./gradlew build` |
| frontend | `cd frontend && npm run lint` 및 영향 페이지 수동 확인 |
| e2e UI | `cd e2e && npm test` 또는 관련 Playwright spec |
| Docker/운영 | `docker compose -f env/docker-compose.yml ps`, 필요한 서비스 로그는 `--tail 50` |

테스트가 환경 의존성 때문에 실패하거나 실행 불가하면, 실패 원인과 미검증 위험을 완료 보고에 적는다.

## 완료 보고

작업 완료 시 `.result/{작업명}/{작업명}.md`를 만든다. 작업명은 2단어 이내로 한다.

필수 항목:

1. 작업 결과
2. 수정 내용
3. 테스트 결과물 위치
4. 수동 테스트 방법
5. 추천 commit message
6. `docs/_index.md` 트리거 맵 기준 갱신한 문서 목록. 없으면 `Doc-Sync: 없음`

문서만 고쳤더라도 `docs/_index.md` 기준으로 어떤 문서를 갱신했는지 명시한다.
