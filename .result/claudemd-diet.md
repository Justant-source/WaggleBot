# CLAUDE.md 다이어트 — 결과 보고

## 1. 작업 결과

CLAUDE.md를 "법전 + 라우터" 구조로 재편. 커밋 기준 10,914 → 7,074 바이트 (**-35%**, 매 세션 ~900토큰 절감 추정). sonnet/opus가 작업 유형을 라우팅 표에 매칭해 필요한 docs만 읽도록 유도하고, 인라인에는 모든 작업에 공통인 사실만 남김.

## 2. 수정 내용

### 구조 재배치 (읽기 순서 최적화)
```
intro + 사용법 2줄 → 문서 라우팅 → 핵심 컨텍스트 → 모듈 맵
→ 하드 제약 → 코딩 규칙 → git 금지 → 기타 → 보고 규칙
```
- 라우팅 표를 **최상단**으로 이동 — 에이전트가 본문 읽기 전에 "어떤 문서를 먼저 읽을지" 결정
- 라우팅 표를 3컬럼(문서/SSOT범위/언제) → 2컬럼(**작업 유형 → 먼저 읽을 문서**)으로 역전 — 작업 매칭이 더 직관적
- intro에 사용 규칙 명시: "상세는 docs가 정본, 충돌 시 last-verified 최신 우선"

### 제거 (docs에 SSOT 존재 → 라우팅으로 대체)
| 제거 항목 | SSOT 위치 |
|----------|-----------|
| 8-Phase 상세 테이블 (입출력 컬럼) | docs/pipeline.md |
| Docker 서비스 9행 테이블 | docs/services.md (포트만 1줄 유지) |
| BGM 경로·자막 프리셋·layout.json SSOT 선언 | docs/config.md |
| 4단계 폴백 상세·I2V 임계값 | docs/pipeline.md, config.md |
| llm-worker invoke 상세 (advisory 파라미터 등) | docs/api.md |
| 설정 분리(crawler.py/monitoring.py re-export) | docs/config.md |

### 유지 (모든 작업 공통 또는 docs에 없는 사실)
- 하드 제약 전체 + ADR 백링크 (Phase 5‖6 병렬 금지사항을 하드 제약으로 승격)
- 코딩 규칙 전체, git/배포 금지 전체, 작업 완료 보고 규칙 전체
- 스코어링 공식 (docs에 없음 — code-only 고아화 방지)
- ScriptData JSON·Mood 9종·볼륨 공유·LLM 라우팅 — 횡단(cross-cutting) 사실
- 모듈 맵 — 탐색 tool call 절약용으로 압축 유지 (15행 → 9행)

### 추가
- "기타" 섹션에 명시: "여기 없는 상세는 docs가 정본 — **추측하지 말고 읽을 것**"

## 3. 테스트 결과물 위치

해당 없음 (문서 작업)

## 4. 수동 테스트 방법

1. `wc -c CLAUDE.md` → 7,074 바이트 확인 (커밋본 10,914 대비 -35%)
2. CLAUDE.md 라우팅 표 — 작업 유형 10행이 docs 9개 + 플러그인 가이드를 커버하는지 확인
3. 새 세션에서 "Phase 7 폴백 수정해줘" 류 요청 → 에이전트가 docs/pipeline.md를 먼저 읽는지 관찰

## 5. 추천 commit message

```
docs: CLAUDE.md 법전+라우터 재편 (-35%, 세션당 토큰 절감)

- 라우팅 표 최상단 이동 + "작업 유형 → 문서" 2컬럼 역전
- docs에 SSOT 있는 상세(서비스 표·8-Phase 상세·BGM/폴백 등) 제거
- 횡단 사실만 핵심 컨텍스트로 압축, 모듈 맵 15→9행
- Phase 5‖6 병렬 금지사항 하드 제약 승격 (ADR-0003 백링크)
```

## 6. DOC-MAP 기준 갱신한 문서 목록

없음 (CLAUDE.md 자체 수정, 코드 변경 없음)
