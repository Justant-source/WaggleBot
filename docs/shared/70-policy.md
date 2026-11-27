# WaggleBot — 정책 및 하드 제약

> last-verified: 2026-11-27 · code-ref: `CLAUDE.md`, `AGENTS.md`, `worker/ai_worker/`, `docs/shared/90-adr/`
> scope: 하드 제약·코딩 금지·git/배포 금지·ADR 연동 — SSOT (비협상)

## 하드 제약 (절대 위반 금지)

AI agent의 작업 시작 절차와 검증 매트릭스는 [`docs/shared/00-agent.md`](00-agent.md)를 따른다. 아래 표는 런타임 안전을 위한 비협상 제약만 다룬다.

| 제약 | 규칙 | 코드 가드 | ADR |
|------|------|-----------|-----|
| **VRAM** | LLM은 원격(claude CLI/API), **TTS는 외부 Local-TTS 제공자(WaggleBot 소유 VRAM 없음, 이전 TTS ~5GB 항목 삭제)** — WaggleBot 로컬 GPU는 VIDEO(~12.7GB)만. 단계 후 `torch.cuda.empty_cache()`+`gc.collect()` | 프로세스 내 로컬 GPU 모델은 `gpu_manager.managed_inference()` 컨텍스트 매니저 **필수**. TTS(외부 서버)·ComfyUI(컨테이너) 호출은 대상 아님 | [ADR-0006](90-adr/0006-local-tts-provider.md) |
| **TTS 제공자 경계** | WaggleBot은 합성 코드·게이트·임대·컨테이너 제어(`docker.sock`)를 갖지 않고 Local-TTS `POST /v1/jobs` 요청만 한다. 서버 장애는 FAILED가 아니라 APPROVED 재큐. 앱 간 import 금지(클라이언트는 복사본) | `ai_worker/tts/synth.py`, `local_tts_client.py` | [ADR-0006](90-adr/0006-local-tts-provider.md) |
| **FFmpeg** | `h264_nvenc` 필수, `libx264` 지정 금지. 렌더러는 filter_complex 단일 NVENC 패스 — 중간 재인코딩 금지 | `renderer/composer.py` | [ADR-0002](90-adr/0002-single-nvenc.md) |
| **ComfyUI** | `--lowvram --reserve-vram 2` 고정, `--normalvram` 금지 (텍스트 인코딩 OOM) | docker-compose 실행 플래그 | [ADR-0001](90-adr/0001-comfyui-lowvram.md) |
| **LTX-2 프레임** | 프레임 수 `1+8k`(9~145), 해상도 8의 배수 | `video_utils.validate_frame_count()` / `validate_resolution()` **필수** | [ADR-0004](90-adr/0004-clip-4-6s-frames-145.md) |
| **Phase 5‖6 병렬** | GPU Phase를 Phase5‖6 병렬에 포함 금지. 순차로 되돌리기도 금지 | `asyncio.gather(tts_phase, video_prompt_phase)` | [ADR-0003](90-adr/0003-phase56-parallel.md) |
| **프리뷰 예외** | 480×854 프리뷰만 CPU 인코딩 허용 | — | [ADR-0002](90-adr/0002-single-nvenc.md) |

## GPU 작업 필수 패턴

```python
with gpu_manager.managed_inference(ModelType.OTHER, "model-name"):
    result = run_local_gpu_model(...)
```

ai_worker 프로세스 안에서 직접 GPU 모델을 올리는 작업은 반드시 컨텍스트 매니저 안에서 실행. 직접 torch 호출 금지. 2026-11-27 기준 이 프로세스에서 `managed_inference`를 호출하는 곳은 없다 — TTS는 외부 Local-TTS 서버 요청(`await synthesize(...)`), 비디오는 ComfyUI 컨테이너 API라서 컨텍스트 매니저 대상이 아니다. 새로 프로세스 내 GPU 모델을 도입하면 이 패턴을 따른다.

## 코딩 금지 규칙

| 금지 | 대신 사용 |
|------|----------|
| `print()` | `logging.getLogger(__name__)` |
| `os.path.*` | `pathlib.Path` |
| `os.getenv()` (로직 내) | `config/` 경유 설정 |
| LLM 직접 HTTP 호출 | `call_llm()` / `call_llm_raw()` 전용 |
| Ollama / qwen2.5 / 로컬 LLM | Claude (haiku / sonnet) 만 |
| `from ai_worker.tts import ...` in `ai_worker/video/` | 독립 파이프라인 — video↛tts import 절대 금지 |
| 사이트 목록 하드코딩 | `CrawlerRegistry.list_crawlers()` 동적 조회 |
| `from ... import ScriptData` (비표준 위치) | `from db.models import ScriptData` |
| 상대경로 import | 절대경로 import (`from ai_worker.llm.transport import call_llm`) |

```python
# DB 항상 with 블록
with SessionLocal() as db:
    post = db.query(Post).filter_by(status=PostStatus.APPROVED).first()
```

- 타입힌트 모든 함수 필수
- 가드절로 중첩 최소화

## git / 배포 금지

작업자의 명령 없이는 자동으로 **절대 수행 금지:**

| 금지 항목 | 이유 |
|----------|------|
| `git commit` · `git push` · `git push --force` | 모든 git 기록 조작 |
| `DROP TABLE` | 데이터 파괴 |
| `/app/media/` 삭제 | 생성 산출물 파괴 |

## video_styles.json 금지 cue

`config/video_styles.json`의 각 mood 스타일에 `forbidden_cues` 목록이 포함될 수 있다. Phase 6 프롬프트 생성 시 forbidden_cue를 포함하는 프롬프트는 폴백 프롬프트로 교체한다.

> 모든 하드 제약의 결정 배경 → [`docs/shared/90-adr/`](90-adr/)
