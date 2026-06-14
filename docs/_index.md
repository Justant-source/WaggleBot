# docs/_index.md — 문서 지도 & Doc-Sync 트리거 맵

> **충돌 해결:** 코드(runtime) > 이 문서 > 하위 docs. 문서 간 충돌은 `last-verified`가 최신인 쪽 우선.

## 계층 인덱스 (C4 줌 순서)

| 계층 | 경로 | last-verified | authority |
|------|------|---------------|-----------|
| 10 Context | [10-context/system-context.md](10-context/system-context.md) | 2026-06-12 | 전역 / 코드 |
| 20 Container | [20-containers/topology.md](20-containers/topology.md) | 2026-06-12 | `env/docker-compose.yml` |
| 20 Config | [20-containers/config.md](20-containers/config.md) | 2026-06-13 | `config/settings.py` |
| 30 Pipeline | [30-components/pipeline.md](30-components/pipeline.md) | 2026-06-13 | `worker/ai_worker/pipeline/content_processor.py` |
| 30 Overview | [30-components/overview.md](30-components/overview.md) | 2026-06-14 | `worker/ai_worker/`, `worker/crawlers/` |
| 30 Status | [30-components/implementation-status.md](30-components/implementation-status.md) | 2026-06-13 | 코드 전역 |
| 40 Data | [40-data/schema.md](40-data/schema.md) | 2026-06-12 | `worker/db/migrations/`, Flyway |
| 50 API Spec | [50-api/rest-spec.md](50-api/rest-spec.md) | 2026-06-12 | backend controller, llm-worker |
| 50 API Flows | [50-api/flows.md](50-api/flows.md) | 2026-06-12 | `worker/llm/LlmController.java` |
| 60 State | [60-runtime/post-state-machine.md](60-runtime/post-state-machine.md) | 2026-06-12 | `worker/db/models.py` PostStatus |
| 60 Runtime | [60-runtime/pipeline-runtime.md](60-runtime/pipeline-runtime.md) | 2026-06-13 | `worker/ai_worker/core/processor.py` |
| 70 Policy | [70-policy/constraints.md](70-policy/constraints.md) | 2026-06-14 | CLAUDE.md / ADR |
| 90 ADR | [90-adr/](90-adr/) | — | 결정 기록 |

---

## 트리거 맵 — 코드 변경 → 갱신할 문서

> §2.1 SSOT Doc-Sync 게이트가 이 표를 참조한다.

| 코드 영역 (glob) | 갱신 대상 문서 |
|-----------------|---------------|
| `env/docker-compose.yml` (서비스·포트·볼륨) | `20-containers/topology.md`, README 포트표 |
| `config/settings.py`, `config/pipeline.json` | `20-containers/config.md` |
| `config/scene_policy.json`, `config/video_styles.json` | `20-containers/config.md` |
| `worker/db/models.py`, `worker/db/migrations/**` | `40-data/schema.md` |
| `backend/**/db/migration/**` (Flyway) | `40-data/schema.md` |
| `backend/**/controller/**` | `50-api/rest-spec.md` |
| `worker/llm/**` (llm-worker API 변경) | `50-api/rest-spec.md`, `50-api/flows.md` |
| `worker/ai_worker/pipeline/**`, `scene/**`, `video/**`, `tts/**`, `renderer/**` | `30-components/pipeline.md` |
| `worker/ai_worker/core/processor.py` | `60-runtime/pipeline-runtime.md` |
| `worker/db/models.py` PostStatus 변경 | `60-runtime/post-state-machine.md` |
| `worker/ai_worker/**` (VRAM 배분 변경) | `20-containers/topology.md` (VRAM pie) |
| 하드 제약 추가·변경·제거 | `90-adr/` 신규 ADR, `70-policy/constraints.md` |
| 크롤러 플러그인 추가 | `30-components/implementation-status.md`, `30-components/overview.md` |
| `env/.env` 환경변수 추가 | `20-containers/config.md`, `20-containers/topology.md` |
| `CLAUDE.md` 라우팅/규칙 변경 | `70-policy/constraints.md`, 이 파일(`_index.md`) |

---

## docs/90-adr/ 현황

| 번호 | 파일 | 결정 요약 |
|------|------|-----------|
| 0001 | [0001-comfyui-lowvram.md](90-adr/0001-comfyui-lowvram.md) | ComfyUI `--lowvram` 고정, `--normalvram` 금지 |
| 0002 | [0002-single-nvenc.md](90-adr/0002-single-nvenc.md) | 렌더러 NVENC 단일 패스 (filter_complex 통합) |
| 0003 | [0003-phase56-parallel.md](90-adr/0003-phase56-parallel.md) | Phase 5(TTS)+6(video_prompt) asyncio.gather 병렬 |
| 0004 | [0004-clip-4-6s-frames-145.md](90-adr/0004-clip-4-6s-frames-145.md) | 클립 4~6초 정책 + 동적 프레임 상한 145 |
| 0005 | [0005-openaudio-s1-mini.md](90-adr/0005-openaudio-s1-mini.md) | TTS OpenAudio S1-mini 업그레이드 + reference_id 음성 구조 |

> 결정 배경 노트 → [90-adr/design-notes.md](90-adr/design-notes.md)

---

## pre-push 체크리스트 (수동)

1. 위 트리거 맵에서 변경한 코드 영역 → 대응 문서 식별
2. 대응 문서 + README.md 갱신 후 `last-verified` 날짜 업데이트 — **같은 커밋**
3. `python scripts/lint_docs.py` 통과 확인
4. 신규 하드 제약 발생 시 → `90-adr/` ADR 작성 + `70-policy/constraints.md` 갱신
5. 갱신 없으면 커밋 메시지에 `Doc-Sync: 없음` 명시
