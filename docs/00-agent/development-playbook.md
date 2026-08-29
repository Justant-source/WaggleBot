# WaggleBot — AI Agent 개발 플레이북

> last-verified: 2026-06-25 · code-ref: `AGENTS.md`, `CLAUDE.md`, `docs/_index.md`, 코드 전역
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
| Python worker | `cd worker && PYTHONPATH=<repo>:<repo>/worker ../venv/bin/pytest test/ -m 'not requires_ffmpeg'` ※ config·ffmpeg 의존 테스트는 컨테이너용 (아래 참고) |
| LLM/파이프라인 | 관련 unit test + `worker/ai_worker/llm/transport.py` call_type 라우팅 확인 |
| backend | `cd backend && ./gradlew test` 또는 최소 `./gradlew build` |
| frontend | `cd frontend && npm run lint` 및 영향 페이지 수동 확인 |
| e2e UI | `cd e2e && npm test` 또는 관련 Playwright spec |
| Docker/운영 | `docker compose -f env/docker-compose.yml ps`, 필요한 서비스 로그는 `--tail 50` |

테스트가 환경 의존성 때문에 실패하거나 실행 불가하면, 실패 원인과 미검증 위험을 완료 보고에 적는다.

### pytest 환경 설정 (Python worker 테스트)

**문제**: 테스트 코드가 `_PROJECT_ROOT = Path(__file__).resolve().parent.parent`로 설정 파일 경로를 계산하므로,  
`worker/` 디렉토리를 기준으로 `config/` 디렉토리를 찾는다. 그러나 실제로는 저장소 루트의 `config/` 디렉토리가 대상이다.

즉 테스트는 **컨테이너 레이아웃**(`/app/ai_worker/…` + `/app/config`)을 전제로 쓰였다.
호스트는 `worker/ai_worker/…` + `<repo>/config` 라 한 단계 어긋난다.

**호스트에서 (대부분의 테스트)**

```bash
cd ~/Data/WaggleBot/worker
PYTHONPATH=/home/justant/Data/WaggleBot:/home/justant/Data/WaggleBot/worker \
  ../venv/bin/pytest test/ -m 'not requires_ffmpeg'
```

- 호스트 python에는 pytest·dotenv가 없다. 반드시 `../venv/bin/pytest`.
- `-m 'not requires_ffmpeg'`: ffmpeg는 컨테이너(`env-ai_worker-1`)에만 있다.
- 약 283개 통과. 아래 두 부류는 **호스트에서 실패하는 게 정상**이다:
  - `config/` 의존: `test_layout.py` · `test_layout_chars.py` · `test_scene_policy.py` · `test_progressive_comments.py`
  - ffmpeg 의존: `test_loudnorm_*.py`

**컨테이너에서 (config·ffmpeg 의존 테스트)**

컨테이너는 경로가 맞고 ffmpeg도 있다. 다만 pytest가 없으므로, pytest 없이 도는
스모크 스크립트를 쓰거나 필요할 때만 컨테이너에 pytest를 넣어 돌린다.

```bash
docker exec env-ai_worker-1 python3 /app/test/smoke_tonel.py
docker exec env-ai_worker-1 python3 /app/test/smoke_sibom_motion.py
docker exec env-ai_worker-1 python3 /app/test/smoke_intro_v2.py  # v2 인트로 폰트/대비/스텝닷/등장모션(2026-08-29)
```

> 🚨 **`worker/config` (root 소유 빈 디렉토리)를 지우거나 바꾸지 말 것.**
> 컴포즈가 `worker → /app` 위에 `config → /app/config` 를 **중첩 마운트**하기 때문에,
> Docker가 컨테이너 기동 시 마운트 지점으로 `worker/config` 를 root 권한으로 만든다.
> 호스트에서는 비어 보이지만 **컨테이너에서 설정 파일이 보이려면 반드시 있어야 하는
> 자리**다. 지우면 `/app/config` 가 통째로 사라진다(빈 디렉토리라 git에도 안 잡혀
> 지운 흔적이 남지 않는다). 복구는 `docker restart env-ai_worker-1`.
>
> 🚨 **`worker/` 안에 `config` 심볼릭 링크를 만들지 말 것.**
> `worker/`는 컨테이너에 `/app`으로 bind mount된다. 거기에 `config` 심볼릭 링크를
> 만들면 별도 bind mount인 `/app/config`를 가려서 **컨테이너에서 설정 파일이
> 통째로 사라진다**(2026-08-21 실제로 발생 — 마운트 지점을 링크로 덮었다가
> 그 링크를 지우면서 마운트 지점까지 사라졌다. 컨테이너 재기동으로 복구). 
> 같은 계열의 사고 전례가 또 있다(테스트용 심볼릭 링크 → 재시작 시 크래시루프).
> 호스트에서 그 테스트들을 꼭 돌려야 한다면 심볼릭 링크 대신 **저장소 사본**에서 돌려라.
>
> 🚨 **정리한다고 `git checkout .` / `git restore .` 을 쓰지 말 것.**
> 추적 중인 파일의 **미커밋 변경을 전부 지운다.** 다른 세션의 진행 중 작업이
> 함께 날아간다. 만든 파일만 이름을 지정해 지울 것.

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
