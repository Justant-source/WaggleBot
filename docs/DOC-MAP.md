# WaggleBot — 변경 → 문서 매핑 (DOC-MAP)

> 작업 완료 후, 이 표 좌측에 해당하는 파일을 수정했다면 우측 문서를 갱신한다.
> `.result/*.md` 보고서의 "갱신한 문서 목록" 항목에 기록.

| 변경한 파일/영역 | 반드시 갱신할 문서 |
|----------------|------------------|
| `env/docker-compose.yml` (서비스·포트·볼륨) | [`docs/services.md`](services.md) |
| `config/settings.py` 변수 추가·삭제 | [`docs/config.md`](config.md) |
| `config/pipeline.json` 키 추가·변경 | [`docs/config.md`](config.md) |
| `config/scene_policy.json`, `video_styles.json` | [`docs/config.md`](config.md) |
| `worker/db/models.py`, Flyway 마이그레이션 | [`docs/database.md`](database.md) |
| `backend/.../controller/` 엔드포인트 추가·변경 | [`docs/api.md`](api.md) |
| `worker/llm/` (llm-worker API 변경) | [`docs/api.md`](api.md) |
| Phase 1~8 로직 (`pipeline/`, `scene/`, `video/`, `tts/`, `renderer/`) | [`docs/pipeline.md`](pipeline.md) |
| 기능 완성·제거·버그 픽스 배치 | [`docs/implementation-status.md`](implementation-status.md) |
| VRAM 배분 변경, 상태 전이 변경 | [`docs/architecture.md`](architecture.md) |
| 하드 제약 추가·변경·제거 | [`docs/adr/`](adr/) 신규 ADR 생성 |
| 크롤러 플러그인 추가 | [`docs/implementation-status.md`](implementation-status.md) |
| `env/.env` 환경변수 추가 | [`docs/config.md`](config.md), [`docs/services.md`](services.md) |

## pre-push 체크리스트 (수동)

1. 변경한 소스가 위 표 좌측에 매칭되는가?
2. 해당 우측 문서를 갱신하고 `last-verified` 날짜·커밋을 업데이트했는가?
3. `docs/implementation-status.md` 버그 픽스 이력이 최신인가?
4. 신규 하드 제약이 생겼다면 `docs/adr/`에 ADR을 작성했는가?

## docker-compose ↔ services.md 정합성 확인

서비스 추가·삭제 시 아래 두 곳이 일치해야 한다:
- `env/docker-compose.yml` `services:` 블록
- `docs/services.md` 서비스 상세 섹션

## docs/adr/ 현황

| 번호 | 파일 | 결정 요약 |
|------|------|-----------|
| 0001 | [0001-comfyui-lowvram.md](adr/0001-comfyui-lowvram.md) | ComfyUI `--lowvram` 고정, `--normalvram` 금지 |
| 0002 | [0002-single-nvenc.md](adr/0002-single-nvenc.md) | 렌더러 NVENC 단일 패스 (filter_complex 통합) |
| 0003 | [0003-phase56-parallel.md](adr/0003-phase56-parallel.md) | Phase 5(TTS)+6(video_prompt) asyncio.gather 병렬 |
| 0004 | [0004-clip-4-6s-frames-145.md](adr/0004-clip-4-6s-frames-145.md) | 클립 4~6초 정책 + 동적 프레임 상한 145 |
