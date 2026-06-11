# WaggleBot — CLAUDE.md

커뮤니티 게시글 → LLM 대본 → TTS → LTX-2 비디오 → FFmpeg 렌더링 → YouTube 자동 업로드 파이프라인.

이 파일은 **불변 규칙 + 라우팅**만 담는다. 상세 사실의 정본(SSOT)은 `docs/`이다.
작업 유형에 맞는 문서를 **먼저 읽고** 시작할 것. 문서 간 충돌 시 `last-verified`가 최신인 쪽을 따른다.

## 문서 라우팅 — 작업 유형별 필독

| 작업 유형 | 먼저 읽을 문서 |
|----------|--------------|
| Phase 1~8 로직, 씬/대본/TTS/비디오/렌더링/폴백 | [docs/pipeline.md](docs/pipeline.md) |
| DB 모델 변경, 마이그레이션, 쿼리 작성 | [docs/database.md](docs/database.md) |
| backend·llm-worker API 추가/수정 | [docs/api.md](docs/api.md) |
| docker-compose, 포트/볼륨/환경변수 | [docs/services.md](docs/services.md) |
| settings.py·pipeline.json·.env 설정 | [docs/config.md](docs/config.md) |
| 전체 구조, 상태 전이, VRAM 배분 | [docs/architecture.md](docs/architecture.md) |
| 구현 현황·버그 픽스 이력 확인 | [docs/implementation-status.md](docs/implementation-status.md) |
| 하드 제약을 수정·우회하려는 경우 (**필독**) | [docs/adr/](docs/adr/) |
| 크롤러/업로더 플러그인 추가 | `worker/crawlers/ADDING_CRAWLER.md` · `worker/uploaders/ADDING_UPLOADER.md` |
| 작업 완료 후 갱신할 문서 판단 | [docs/DOC-MAP.md](docs/DOC-MAP.md) |

## 핵심 컨텍스트 (모든 작업 공통)

- **상태 전이:** COLLECTED → EDITING → APPROVED → PROCESSING → PREVIEW_RENDERED → RENDERED → UPLOADED (↕ DECLINED/FAILED)
- **8-Phase:** ①analyze_resources → ②chunk_with_llm → ③validate_and_fix → ④SceneDirector → ④.5 assign_video_modes → ⑤TTS ‖ ⑥video_prompt (병렬) → ⑦video_clip(ComfyUI) → ⑧FFmpeg 렌더링. Phase 4.5~7은 `VIDEO_GEN_ENABLED=true`일 때만. <!-- SSOT: docs/pipeline.md -->
- **LLM 호출:** 전부 `worker/ai_worker/llm/transport.py`의 `call_llm()` 경유. `pick_model()` 라우팅 — chunk/generate_script/scene_director/feedback→**sonnet**, video_prompt/translate/comment_summarize→**haiku**. 백엔드 `cli`(llm-worker :8090, 구독)|`api`(Anthropic 직접) — `pipeline.json`의 `llm_backend`로 전환.
- **ScriptData:** `Content.summary_text`에 JSON 저장. 문자열이면 레거시.
- **스코어링:** `Post.engagement_score` = 조회×0.1 + 좋아요×2.0 + 댓글×1.5 + 베스트공감×0.5, 6시간 반감기.
- **Mood 9종:** humor·touching·anger·sadness·horror·info·controversy·daily·shock
- **dashboard_worker:** Java backend가 `jobs` 테이블에 enqueue → Python이 execute.
- **볼륨 공유:** ComfyUI `/comfyui/output` ↔ ai_worker `media/tmp/videos` 동일 Docker 볼륨 (비디오 전달 경로).
- **포트:** db 3306 · backend 8080 · frontend 3000 · llm-worker 8090 · fish-speech 8082→8080 · comfyui 8188 <!-- SSOT: docs/services.md -->
- **실행/로그:** `docker compose -f env/docker-compose.yml up -d` · `docker compose logs --tail 50 ai_worker`

## 모듈 맵

| 영역 | 위치 |
|------|------|
| 파이프라인 | `worker/ai_worker/` — core/(main.py 진입, processor.py 루프, gpu_manager.py), pipeline/content_processor.py(Phase 1~8 통합), scene/, script/, tts/, video/, renderer/ |
| LLM | `worker/ai_worker/llm/transport.py` (call_llm·pick_model) · 게이트웨이 `worker/llm/`(Spring Boot, claude CLI 브릿지) |
| 크롤러 | `worker/crawlers/` — base.py(retry+스코어링) + nate_pann·bobaedream·dcinside·fmkorea 플러그인 |
| DB | `worker/db/models.py`(Post/Comment/Content/LLMLog/ScriptData/PostStatus) · `session.py` · `migrations/` |
| 업로더 | `worker/uploaders/` — base.py(UploaderRegistry), youtube.py |
| 대시보드 | `frontend/`(Next.js 14, 7개 어드민 페이지) + `backend/`(Spring Boot+Flyway) + `worker/dashboard_worker/` |
| 분석·모니터링 | `worker/analytics/` · `worker/monitoring/` |
| 텔레그램 | `telegram/` (Node/TS, 선택) |
| 설정 | `config/` — settings.py(허브), crawler.py, monitoring.py, layout.json, scene_policy.json, video_styles.json, pipeline.json |

## 하드 제약 (절대 위반 금지)

**VRAM (RTX 3090 24GB):** LLM은 원격(claude CLI/API) — 로컬 LLM VRAM 없음. 로컬 GPU는 TTS(~5GB)+VIDEO(~12.7GB)=~17GB만. 각 단계 후 `torch.cuda.empty_cache()`+`gc.collect()`. GPU 작업은 컨텍스트 매니저 필수:
```python
with gpu_manager.managed_inference(ModelType.TTS, "fish-speech"):
    result = tts.synthesize(text)
```
**FFmpeg:** `h264_nvenc` 필수, `libx264` 지정 금지 (프리뷰 480×854만 CPU 허용). 렌더러는 filter_complex 단일 NVENC 패스 — 중간 재인코딩 금지 → [ADR-0002](docs/adr/0002-single-nvenc.md)
**ComfyUI:** `--lowvram --reserve-vram 2` 고정, `--normalvram` 금지 (텍스트 인코딩 OOM) → [ADR-0001](docs/adr/0001-comfyui-lowvram.md)
**LTX-2:** 프레임 수 `1+8k`(9~145, 동적 상한 `VIDEO_NUM_FRAMES_MAX`=145), 해상도 8의 배수 — `video_utils.validate_frame_count()`/`validate_resolution()` 필수, 클립 4~6초 정책 → [ADR-0004](docs/adr/0004-clip-4-6s-frames-145.md)
**Phase 5‖6 병렬:** 순차로 되돌리거나 GPU Phase를 병렬에 포함 금지 → [ADR-0003](docs/adr/0003-phase56-parallel.md)

## 코딩 규칙

```python
with SessionLocal() as db:  # DB 항상 with 블록
    post = db.query(Post).filter_by(status=PostStatus.APPROVED).first()
```
- `logging.getLogger(__name__)` — print 금지
- 절대경로 import. ai_worker는 **패키지 경로**: `from ai_worker.llm.transport import call_llm`
- `pathlib.Path` 필수 — os.path 금지
- 설정은 `config/` 경유 — 로직 내 `os.getenv()` 금지
- 타입힌트 모든 함수 필수, 가드절로 중첩 최소화
- LLM 직접 HTTP 호출 금지 → `call_llm()`/`call_llm_raw()`만. **Ollama/qwen2.5 미사용** — Claude만. `call_ollama_raw`는 레거시 별칭
- ScriptData는 `from db.models import ScriptData` (canonical 위치)
- 사이트 목록 하드코딩 금지 → `CrawlerRegistry.list_crawlers()` 동적 조회
- `ai_worker/video`는 `ai_worker/tts` 절대 import 금지 — 독립 파이프라인

## git / 배포 금지

작업자의 명령 없이는 자동으로 **절대 수행 금지:**
- `git commit` · `git push` · `git push --force` — 모든 git 기록 조작
- `DROP TABLE` · `/app/media/` 삭제 — 데이터 파괴

## 기타

- `docs/arch/done/` — 완료된 과거 스펙 · `docs/arch/env/AGENT_TEAM.md` — Agent Team 운영 가이드 v3 (현행)
- 여기 없는 상세(BGM/자막 프리셋, 4단계 폴백, I2V 임계값, VOICE_PRESETS, 모델 파일 등)는 라우팅 표의 해당 docs가 정본 — 추측하지 말고 읽을 것

## 작업 완료 보고 규칙

작업 완료 시 반드시 `.result/{작업이름}.md` 생성 (작업이름 2단어 이하). 양식: `.result/sample/sample.md`
- **필수 항목:** 1. 작업 결과 2. 수정 내용 3. 테스트 결과물 위치 4. 수동 테스트 방법 5. 추천 commit message 6. **DOC-MAP 기준 갱신한 문서 목록** (없으면 "없음")
- `.result/*` 안에는 절대 root 권한으로 write 금지
