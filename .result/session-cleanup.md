# 코드베이스 스캔 — 잡다 버그픽스·문서 동기화

## 1. 작업 결과

미검토 파일(`main.py`, `scheduler.py`, `uploaders/`) 스캔 완료. 버그/규칙 위반 3건 수정, 문서 전반 동기화.

## 2. 수정 내용

### `.gitignore` 보완 (6 entries)

- `worker/test/test_image_filter_output/`, `test_prompt_engine_output/`, `test_video_rendering_output/` — 신규 테스트 모듈이 생성하는 출력 디렉터리 미등록
- `worker/media/` — 런타임 음성·영상 임시파일 디렉터리
- `.claude/config.json`, `.claude/*.lock` — Claude Code 자체 런타임 파일

### `worker/main.py` & `worker/scheduler.py` (CLAUDE.md 코딩 규칙 위반)

`session = SessionLocal(); try: ... finally: session.close()` 패턴 →
`with SessionLocal() as session:` 로 통일.

- **영향**: 기능 동일(SQLAlchemy Session은 `with`에서 `close()`만 호출). 규칙 준수 목적.

### `env/docker-compose.yml` — monitoring 서비스 VRAM 환경변수 누락

`GPU_VRAM_WARNING`, `GPU_VRAM_CRITICAL`이 monitoring 서비스 환경변수에 없었음.
기본값은 코드에서 적용되나 Docker 환경에서 재정의할 수 없었던 상태. 추가.

### `docs/config.md` — 모니터링 설정 섹션 신규 추가

`GPU_VRAM_WARNING/CRITICAL` 등 `config/monitoring.py` 설정 10개가 문서에 없었음.
"### 모니터링 설정" 테이블 추가, `last-verified` → 2026-06-12.

### `docs/services.md` — monitoring 서비스 GPU_VRAM 항목 추가

docker-compose 변경에 맞춰 `GPU_VRAM_WARNING=85 / GPU_VRAM_CRITICAL=95` 추가.

### 나머지 docs last-verified 일괄 갱신

`docs/implementation-status.md`, `api.md`, `architecture.md`, `pipeline.md`, `database.md`, `improvements.md`의 `last-verified` → 2026-06-12 (`656dffd`).
`implementation-status.md`: "미구현" 표에서 VRAM 모니터링·다크모드 제거(구현 완료), 신규 섹션 추가.

## 3. 테스트 결과물 위치

없음 (설정·문서 변경, 기능 무변경)

## 4. 수동 테스트 방법

```bash
# session with 블록 정상 동작 확인
docker compose -f env/docker-compose.yml exec crawler python main.py --list

# VRAM 모니터링 env 확인
docker compose -f env/docker-compose.yml config | grep GPU_VRAM

# gitignore 확인
git status --short  # worker/media 등이 untracked에서 사라짐
```

## 5. 추천 commit message

```
chore: SessionLocal with블록 통일 + .gitignore 보완 + VRAM 모니터링 env/docs 동기화
```

## 6. DOC-MAP 기준 갱신한 문서 목록

- `docs/config.md` — 모니터링 설정 섹션 추가 (`config/settings.py` 변수 변경 → config.md 갱신 규칙)
- `docs/services.md` — monitoring 서비스 GPU_VRAM env 추가 (`docker-compose.yml` 변경 → services.md 갱신 규칙)
- `docs/implementation-status.md` — 미구현 표 정리, 신규 구현 기록 추가 (버그픽스 배치 → implementation-status 갱신 규칙)
- `docs/api.md`, `docs/architecture.md`, `docs/pipeline.md`, `docs/database.md`, `docs/improvements.md` — last-verified 날짜 갱신
