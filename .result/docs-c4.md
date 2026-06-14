# docs-c4 — C4 SSOT 문서 마이그레이션 결과

## 1. 작업 결과

WaggleBot `docs/`를 번호 C4 계층(`10~90`)으로 재편, SSOT Doc-Sync 게이트를 CLAUDE.md에 추가, 6개 검사 lint 도구 신설. `python3 scripts/lint_docs.py` **6/6 통과**.

### DoD 체크리스트
- [x] 루트에 `CLAUDE.md`·`README.md`·`AGENTS.md`만
- [x] `docs/`가 `10~90` 번호 계층 + `_index.md` 트리거 맵 존재 (DOC-MAP.md 삭제됨)
- [x] 모든 다이어그램 GitHub 네이티브(C4Context 0건), 인라인, `last-verified`/`code-ref` 헤더 부착
- [x] CLAUDE.md SSOT Doc-Sync 게이트 + 번호 라우팅, 114줄 (< 180), `@.claude/rules/llm-safety.md` import
- [x] `python3 scripts/lint_docs.py` 6개 검사 통과
- [x] README에 L1 Context 다이어그램 인라인

## 2. 수정 내용

### git mv (히스토리 보존)
| 이전 | 이후 |
|------|------|
| `docs/services.md` | `docs/20-containers/topology.md` |
| `docs/config.md` | `docs/20-containers/config.md` |
| `docs/implementation-status.md` | `docs/30-components/implementation-status.md` |
| `docs/database.md` | `docs/40-data/schema.md` |
| `docs/improvements.md` | `docs/90-adr/design-notes.md` |
| `docs/adr/000[1-5]-*.md` | `docs/90-adr/000[1-5]-*.md` (5개) |

### git rm (분할 후 원본 삭제)
- `docs/architecture.md` → 10-context + 20-containers + 60-runtime 으로 분할
- `docs/pipeline.md` → 30-components + 60-runtime 으로 분할
- `docs/api.md` → 50-api/rest-spec + 50-api/flows 으로 분할
- `docs/DOC-MAP.md` → `docs/_index.md`로 흡수·삭제

### 신규 생성 (19개 파일)
```
docs/_index.md                        # 문서 지도 + 트리거 맵 (DOC-MAP 대체)
docs/10-context/system-context.md     # L1 시스템 컨텍스트 flowchart
docs/20-containers/topology.md        # L2 서비스 레이어 + VRAM + 기술스택 + 배포 (통합)
docs/30-components/overview.md        # L3 모듈 책임 flowchart (신규)
docs/30-components/pipeline.md        # 8-Phase 컴포넌트 책임
docs/50-api/rest-spec.md              # 엔드포인트 명세 표
docs/50-api/flows.md                  # invoke sequenceDiagram + JSON Mode flowchart
docs/60-runtime/post-state-machine.md # Post 상태 전이 stateDiagram
docs/60-runtime/pipeline-runtime.md   # 처리 루프 + 4단계 폴백 + Phase5‖6 시퀀싱 + 피드백
docs/70-policy/constraints.md         # 하드 제약 + 코딩금지 + git금지 (신규)
.claude/rules/llm-safety.md           # LLM 안전 규칙 (항상 로드)
scripts/lint_docs.py                  # 6개 검사 linter
AGENTS.md                             # CLAUDE.md 심링크
```

### 수정 (기존 파일)
- `CLAUDE.md`: `@import` 추가, Doc-Sync 게이트 추가, 라우팅 표 번호 경로로 교체, stale 참조 제거 (94→114줄)
- `README.md`: L1 Context mermaid 다이어그램 인라인 추가
- `docs/20-containers/topology.md`: architecture.md L2 내용(서비스 레이어·VRAM·기술스택) 병합
- `docs/40-data/schema.md`: ScriptData 정정(테이블 아님→@dataclass), authority 헤더 추가
- `docs/30-components/implementation-status.md`, `docs/20-containers/config.md`, `docs/90-adr/design-notes.md`: ADR 상대 링크 수정 (`adr/` → `../90-adr/`)

### 주요 수정 사항 (ScriptData 정정)
`ScriptData`는 DB 테이블이 아닌 Python `@dataclass`. `Content.summary_text` 컬럼에 JSON 직렬화 저장. `40-data/schema.md`에 명시 정정.

## 3. 테스트 결과물 위치

```
scripts/lint_docs.py    — 검증 스크립트
docs/                   — 재편된 문서 트리
```

## 4. 수동 테스트 방법

```bash
# lint 6개 검사
python3 scripts/lint_docs.py

# CLAUDE.md 줄 수
wc -l CLAUDE.md                        # 114 (< 180)

# 루트 md 3개만
ls *.md                                # AGENTS.md CLAUDE.md README.md

# C4Context 0건
grep -rn "C4Context\|C4Container" docs/   # 매치 없음

# AGENTS.md 심링크
readlink AGENTS.md                     # → CLAUDE.md

# mermaid 렌더 확인 (VS Code 또는 GitHub)
# 주요 파일: docs/10-context/system-context.md
#           docs/60-runtime/post-state-machine.md
#           docs/30-components/overview.md
#           README.md (L1 Context)
```

## 5. 추천 commit message

```
docs: C4 번호 계층 마이그레이션 + SSOT Doc-Sync 게이트

- docs/ → 10-context/20-containers/30-components/40-data/50-api/60-runtime/70-policy/90-adr
- architecture/pipeline/api.md 충실 분할 (3+2+2 → 9개)
- docs/_index.md: 트리거 맵 + ADR 인덱스 (DOC-MAP.md 흡수)
- CLAUDE.md: Doc-Sync 게이트 + 번호 라우팅 + @import rules (114줄)
- AGENTS.md: CLAUDE.md 심링크 (크로스툴 호환)
- scripts/lint_docs.py: 6개 검사 linter 신설
- README.md: L1 Context mermaid 인라인
- 40-data/schema.md: ScriptData=@dataclass 정정
- python3 scripts/lint_docs.py PASS
```

## 6. `docs/_index.md` 트리거 맵 기준 갱신한 문서 목록

이 작업 자체가 문서 구조 전체를 재편한 것이므로 아래 전체가 갱신됨:

| 갱신 문서 | 변경 내용 |
|----------|----------|
| `docs/_index.md` | 신규 생성 (DOC-MAP 흡수) |
| `docs/10-context/system-context.md` | 신규 (architecture.md 분할) |
| `docs/20-containers/topology.md` | 내용 보강 (services.md + architecture L2 통합) |
| `docs/20-containers/config.md` | 이동 (ADR 링크 수정) |
| `docs/30-components/pipeline.md` | 신규 (pipeline.md 분할) |
| `docs/30-components/overview.md` | 신규 |
| `docs/30-components/implementation-status.md` | 이동 (ADR 링크 수정) |
| `docs/40-data/schema.md` | 이동 + ScriptData 정정 + authority 헤더 |
| `docs/50-api/rest-spec.md` | 신규 (api.md 분할) |
| `docs/50-api/flows.md` | 신규 (api.md 분할) |
| `docs/60-runtime/post-state-machine.md` | 신규 (architecture.md 분할) |
| `docs/60-runtime/pipeline-runtime.md` | 신규 (pipeline.md 분할) |
| `docs/70-policy/constraints.md` | 신규 |
| `docs/90-adr/design-notes.md` | 이동 (ADR 링크 수정) |
| `docs/90-adr/000[1-5]-*.md` | 이동 (5개) |
| `CLAUDE.md` | Doc-Sync 게이트 + 번호 라우팅 + stale 참조 제거 |
| `README.md` | L1 Context mermaid 추가 |
