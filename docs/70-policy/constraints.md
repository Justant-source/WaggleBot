# WaggleBot — 정책 및 하드 제약

> last-verified: 2026-06-14 · code-ref: `CLAUDE.md`, `worker/ai_worker/`, `docs/90-adr/`
> scope: 하드 제약·코딩 금지·git/배포 금지·ADR 연동 — SSOT (비협상)

## 하드 제약 (절대 위반 금지)

| 제약 | 규칙 | 코드 가드 | ADR |
|------|------|-----------|-----|
| **VRAM** | LLM은 원격(claude CLI/API) — 로컬 GPU는 TTS(~5GB)+VIDEO(~12.7GB)=~17GB만. 단계 후 `torch.cuda.empty_cache()`+`gc.collect()` | `gpu_manager.managed_inference()` 컨텍스트 매니저 **필수** | — |
| **FFmpeg** | `h264_nvenc` 필수, `libx264` 지정 금지. 렌더러는 filter_complex 단일 NVENC 패스 — 중간 재인코딩 금지 | `renderer/composer.py` | [ADR-0002](../90-adr/0002-single-nvenc.md) |
| **ComfyUI** | `--lowvram --reserve-vram 2` 고정, `--normalvram` 금지 (텍스트 인코딩 OOM) | docker-compose 실행 플래그 | [ADR-0001](../90-adr/0001-comfyui-lowvram.md) |
| **LTX-2 프레임** | 프레임 수 `1+8k`(9~145), 해상도 8의 배수 | `video_utils.validate_frame_count()` / `validate_resolution()` **필수** | [ADR-0004](../90-adr/0004-clip-4-6s-frames-145.md) |
| **Phase 5‖6 병렬** | GPU Phase를 Phase5‖6 병렬에 포함 금지. 순차로 되돌리기도 금지 | `asyncio.gather(tts_phase, video_prompt_phase)` | [ADR-0003](../90-adr/0003-phase56-parallel.md) |
| **프리뷰 예외** | 480×854 프리뷰만 CPU 인코딩 허용 | — | [ADR-0002](../90-adr/0002-single-nvenc.md) |

## GPU 작업 필수 패턴

```python
with gpu_manager.managed_inference(ModelType.TTS, "fish-speech"):
    result = tts.synthesize(text)
```

GPU 작업은 반드시 컨텍스트 매니저 안에서 실행. 직접 torch 호출 금지.

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

> 모든 하드 제약의 결정 배경 → [`docs/90-adr/`](../90-adr/)
