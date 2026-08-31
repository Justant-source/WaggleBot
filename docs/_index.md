---
title: docs — 문서 지도 & Doc-Sync 트리거 맵
last_updated: 2026-08-31
---

# docs/_index.md — 문서 지도 & Doc-Sync 트리거 맵

> **SSOT 해결 규칙**: 충돌 시 **코드(runtime) > 이 문서 > 다른 문서** 순으로 우선한다.
> 새 컨텍스트를 시작할 때 이 파일을 첫 번째로 읽는다.

## §1. 계층 인덱스 (대분류 × 계층)

| 계층 | `backend/` | `frontend/` | `telegram/` | `worker/` | `shared/` |
|---|---|---|---|---|---|
| **00** agent | — | — | — | — | `00-agent.md` |
| **10** context | — | — | — | — | `10-context.md` 🏛 |
| **20** containers | — | — | — | `20-containers.md` | `20-containers.md` 🏛 |
| **30** components | — | — | — | `30-components/` (3) | — |
| **40** data | — | — | — | — | `40-data.md` 🏛 |
| **50** api | `50-api.md` | — | — | `50-api.md` | — |
| **60** runtime | — | — | — | `60-runtime.md` | `60-runtime.md` 🏛 |
| **70** policy | — | — | — | — | `70-policy.md` 🏛 |
| **90** adr | — | — | — | — | `90-adr/` (6) 🏛 |

경로 접두 `docs/<대분류>/`. frontend·telegram 문서는 없다 (빈 껍데기 금지). compose는 `docs/` 를 마운트하지 않는다.

## §2. 작업별 진입 문서

| 작업 | 1차 진입(이것만 읽기) | 2차(필요 시) | 실제 코드 확인 |
|---|---|---|---|
| 에이전트 작업 절차 | `docs/shared/00-agent.md` | `docs/_index.md` | `AGENTS.md` |
| 시스템 전체 그림 | `docs/shared/10-context.md` | `docs/shared/20-containers.md` | `env/docker-compose.yml` |
| 배포 · 포트 · VRAM | `docs/shared/20-containers.md` | `docs/worker/20-containers.md` | `env/docker-compose.yml` |
| worker 설정 | `docs/worker/20-containers.md` | `docs/shared/20-containers.md` | `config/settings.py` |
| 파이프라인 Phase | `docs/worker/30-components/pipeline.md` | `docs/worker/60-runtime.md` | `worker/ai_worker/pipeline/content_processor.py` |
| 모듈 · 크롤러 | `docs/worker/30-components/overview.md` | `docs/worker/30-components/implementation-status.md` | `worker/ai_worker/` · `worker/crawlers/` |
| DB 스키마 | `docs/shared/40-data.md` | — | `worker/db/migrations/` · `backend/src/main/resources/db/migration/` |
| Backend REST | `docs/backend/50-api.md` | `docs/worker/50-api.md` | `backend/src/main/java/com/wagglebot/controller/` |
| llm-worker 흐름 | `docs/worker/50-api.md` | `docs/backend/50-api.md` | `worker/llm/src/main/java/com/wagglebot/llmworker/LlmController.java` |
| Post 상태 전이 | `docs/shared/60-runtime.md` | `docs/worker/60-runtime.md` | `worker/db/models.py` |
| 처리 루프 · 폴백 | `docs/worker/60-runtime.md` | `docs/worker/30-components/pipeline.md` | `worker/ai_worker/core/processor.py` |
| 하드 제약 | `docs/shared/70-policy.md` | `docs/shared/90-adr/` | ADR `related_code` |
| ADR | `docs/shared/90-adr/` | `docs/shared/90-adr/design-notes.md` | — |

## §4. 문서 권위 그래프

| 충돌 | 이긴 쪽 |
|---|---|
| 코드 vs 문서 | 코드 |
| 이 파일 vs 다른 문서 | 이 파일 |
| `docs/shared/70-policy.md` vs `AGENTS.md` 제약 표 | `docs/shared/70-policy.md` |

## §5. Doc-Sync 트리거 맵

| # | 코드 영역 (glob) | 갱신 대상 문서 | 등급 |
|---|---|---|---|
| 1 | `AGENTS.md` | `docs/shared/70-policy.md` · `docs/_index.md` · `docs/shared/00-agent.md` | M |
| 2 | `env/docker-compose.yml` | `docs/shared/20-containers.md` · `README.md` | M |
| 3 | `config/settings.py` | `docs/worker/20-containers.md` | M |
| 4 | `config/pipeline.json` | `docs/worker/20-containers.md` | M |
| 5 | `config/scene_policy.json` | `docs/worker/20-containers.md` | M |
| 6 | `config/video_styles.json` | `docs/worker/20-containers.md` | M |
| 7 | `worker/db/models.py` | `docs/shared/40-data.md` · `docs/shared/60-runtime.md` | M |
| 8 | `worker/db/migrations/**` | `docs/shared/40-data.md` | M |
| 9 | `backend/src/main/resources/db/migration/**` | `docs/shared/40-data.md` | M |
| 10 | `backend/src/main/java/com/wagglebot/controller/**` | `docs/backend/50-api.md` | M |
| 11 | `worker/llm/**` | `docs/backend/50-api.md` · `docs/worker/50-api.md` | M |
| 12 | `worker/ai_worker/pipeline/**` | `docs/worker/30-components/pipeline.md` | M |
| 13 | `worker/ai_worker/scene/**` | `docs/worker/30-components/pipeline.md` | M |
| 14 | `worker/ai_worker/video/**` | `docs/worker/30-components/pipeline.md` | M |
| 15 | `worker/ai_worker/tts/**` | `docs/worker/30-components/pipeline.md` | M |
| 16 | `worker/ai_worker/renderer/**` | `docs/worker/30-components/pipeline.md` | M |
| 17 | `worker/ai_worker/core/processor.py` | `docs/worker/60-runtime.md` | M |
| 18 | `worker/crawlers/**` | `docs/worker/30-components/overview.md` · `docs/worker/30-components/implementation-status.md` | C |
| 19 | 하드 제약 추가·변경 | `docs/shared/90-adr/` · `docs/shared/70-policy.md` | M |

## §6. Code → Docs 역인덱스

| 코드 경로 접두 | 소유 모듈 | 먼저 읽을 문서 | 권위본 |
|---|---|---|---|
| `worker/ai_worker/pipeline/**` | worker | `docs/worker/30-components/pipeline.md` | 🏛 |
| `worker/ai_worker/core/processor.py` | worker | `docs/worker/60-runtime.md` | |
| `worker/ai_worker/scene/**` | worker | `docs/worker/30-components/pipeline.md` | |
| `worker/llm/src/main/java/com/wagglebot/llmworker/LlmController.java` | worker | `docs/worker/50-api.md` | |
| `backend/src/main/java/com/wagglebot/controller/**` | backend | `docs/backend/50-api.md` | |
| `worker/db/models.py` | shared | `docs/shared/40-data.md` | `docs/shared/60-runtime.md` |
| `env/docker-compose.yml` | shared | `docs/shared/20-containers.md` | |
| `config/settings.py` | worker | `docs/worker/20-containers.md` | |
| `scripts/lint_docs.py` | shared | 이 파일. 검사 4·5·10이 링크와 코드 glob 실재를 본다. | |
