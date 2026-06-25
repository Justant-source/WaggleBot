# Docs Update Result

## 1. 작업 결과

AI agent가 WaggleBot을 개발할 때 필요한 탐색 순서, 하위 시스템 진입점, 검증 기준을 문서화하고 기존 문서의 코드 기준 드리프트를 정리했다.

## 2. 수정 내용

- `docs/00-agent/development-playbook.md` 신규 추가: agent 작업 시작 순서, 시스템별 진입점, 불변 규칙 체크리스트, 검증 매트릭스, 완료 보고 규칙.
- `CLAUDE.md`/`AGENTS.md` 라우팅 보정: 실제 docs 경로, ADR 경로, `python3` lint 명령, 크롤러/업로더 현황, `.result/{작업명}/{작업명}.md` 형식 반영.
- `README.md` 보정: OpenAudio S1-mini TTS, 7개 크롤러, TikTok 업로더, 참조 음성 등록 방식, 현재 docs 계층 링크 반영.
- `docs/_index.md` 갱신: 00 Agent 계층 추가, root/docs-only 변경 트리거 추가, 갱신 문서 last-verified 반영.
- 컨테이너/설정/컴포넌트/API/DB/정책/ADR 문서의 확인된 드리프트 수정.

## 3. 테스트 결과물 위치

- 별도 산출물 없음. 검증 결과는 이 보고서와 터미널 실행 결과 기준.

## 4. 수동 테스트 방법

```bash
python3 scripts/lint_docs.py
rg -n "docs/services|docs/pipeline|docs/adr|docs/architecture|docs/database|docs/api|docs/config|docs/implementation-status|docs/improvements|VOICE_PRESETS.*settings\\.py|PROCESS_POST|REGENERATE_SCRIPT|DONE / FAILED|python scripts/lint_docs|llm-worker/|YouTube 업로더|2026-06-11 기준|v1\\.5\\.1 API|FISH_SPEECH_TIMEOUT = 120|TEMPERATURE = 0\\.5|REPETITION_PENALTY = 1\\.3|voices.json v2" docs README.md AGENTS.md CLAUDE.md
```

## 5. 추천 commit message

```text
docs: improve agent development guidance and sync docs drift
```

## 6. docs/_index.md 트리거 맵 기준 갱신한 문서 목록

- `AGENTS.md`, `CLAUDE.md` 라우팅/규칙 변경: `docs/70-policy/constraints.md`, `docs/_index.md`, `docs/00-agent/development-playbook.md`
- `README.md` 구조·설치·링크 변경: `README.md`, `docs/_index.md`, 관련 SSOT 문서
- `docs/00-agent/**`: `docs/_index.md`, `AGENTS.md`/`CLAUDE.md`
- `env/docker-compose.yml` 관련 문서 정합성: `docs/20-containers/topology.md`, `README.md`
- `config/settings.py`, `config/pipeline.json` 관련 문서 정합성: `docs/20-containers/config.md`
- `worker/db/models.py`, backend Flyway 관련 문서 정합성: `docs/40-data/schema.md`
- `backend/**/controller/**`, `worker/llm/**` 관련 문서 정합성: `docs/50-api/rest-spec.md`
- 크롤러/업로더 현황 정합성: `docs/30-components/overview.md`, `docs/30-components/implementation-status.md`
- ADR 관련 링크 정합성: `docs/90-adr/0001-comfyui-lowvram.md`, `docs/90-adr/0003-phase56-parallel.md`, `docs/90-adr/0004-clip-4-6s-frames-145.md`, `docs/90-adr/0005-openaudio-s1-mini.md`
