# 문서 정비 — 결과 보고

## 1. 작업 결과

docs-as-code drift 제거 및 구조적 방지책 도입. 구체적으로:
- **drift 2건 수정** (services.md stale 기술)
- **last-verified 메타데이터** 전 문서(8개)에 추가
- **DOC-MAP.md** 신규 생성 (변경→문서 매핑 + pre-push 체크리스트)
- **ADR 3개** 신규 생성 (하드 제약 이유 문서화)
- **CLAUDE.md 다이어트** (중복 제거 + 라우팅 테이블 "언제" 컬럼 추가)

## 2. 수정 내용

### drift 수정 (docs/services.md)
| 위치 | 이전 | 이후 |
|------|------|------|
| backend 소스 | `(현재 domain 엔티티만 구현)` | `(완전 구현)` |
| frontend 소스 | `(App Router 구조 준비됨, 구현 예정)` | `(완전 구현, 7개 어드민 페이지 운영 중)` |

### last-verified 추가 (8개 docs)
- `docs/architecture.md`, `pipeline.md`, `database.md`, `api.md`
- `docs/services.md`, `config.md`, `implementation-status.md`, `improvements.md`
- 형식: `> **last-verified:** 2026-06-11 (commit 913e606)` + scope 설명

### 신규 파일
- `docs/DOC-MAP.md` — 변경 파일 → 갱신 문서 매핑 표 + pre-push 체크리스트
- `docs/adr/0001-comfyui-lowvram.md` — ComfyUI `--lowvram` 강제 이유
- `docs/adr/0002-single-nvenc.md` — 단일 NVENC 인코딩 이유
- `docs/adr/0003-phase56-parallel.md` — Phase 5‖6 asyncio.gather 이유

### CLAUDE.md 변경
- 상태 전이 ASCII 블록 → 1줄 인라인 + architecture.md 링크
- 8-Phase 서술 → 테이블 + SSOT 주석 + ADR-0003 백링크
- Docker 서비스 표 → 3-컬럼으로 축소 + SSOT 주석 + services.md 링크
- 하드 제약에 ADR 백링크 추가 (ComfyUI→ADR-0001, 단일NVENC→ADR-0002)
- 문서 라우팅 테이블: "내용" 컬럼 → "SSOT 범위" + "읽어야 하는 경우" 2컬럼
- 라우팅에 충돌 해소 규칙 추가: `last-verified` 최신 쪽 우선
- 라우팅에 DOC-MAP, ADR 항목 추가
- 작업 완료 보고 규칙에 "DOC-MAP 기준 갱신한 문서 목록" 항목 추가

## 3. 테스트 결과물 위치

해당 없음 (문서 작업)

## 4. 수동 테스트 방법

1. `cat docs/services.md | grep -A2 "backend\|frontend"` — drift 수정 확인
2. `head -6 docs/architecture.md` — last-verified 메타데이터 확인
3. `ls docs/adr/` — ADR 3개 존재 확인
4. `cat docs/DOC-MAP.md` — DOC-MAP 내용 확인
5. CLAUDE.md 전체 검토 — 라우팅 테이블 "읽어야 하는 경우" 컬럼 확인

## 5. 추천 commit message

```
docs: drift 수정, last-verified·DOC-MAP·ADR 추가, CLAUDE.md 다이어트

- services.md: backend/frontend "구현 예정" → "완전 구현" drift 수정
- 전 문서(8개) last-verified 메타데이터 추가 (충돌 시 최신 우선 규칙)
- docs/DOC-MAP.md 신규: 변경→문서 매핑 + pre-push 체크리스트
- docs/adr/ 신규: 0001(ComfyUI lowvram), 0002(단일NVENC), 0003(Phase56병렬)
- CLAUDE.md: 중복 제거·SSOT 지정·라우팅 테이블 "언제" 컬럼·ADR 백링크
```

## 6. DOC-MAP 기준 갱신한 문서 목록

이 작업 자체가 문서 정비이므로 모든 docs가 갱신됨. 코드 변경 없음.
