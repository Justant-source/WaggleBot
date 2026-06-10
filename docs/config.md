# WaggleBot — 설정 레퍼런스

> **last-verified:** 2026-06-11 (commit `913e606`)
> **scope:** settings.py 변수, pipeline.json, scene_policy.json, layout.json, .env — SSOT

## 설정 파일 구조

```
config/
├── settings.py              # 허브 — 모든 Python 모듈의 설정 진입점
├── crawler.py               # 크롤러 전용 설정 (settings.py에서 re-export)
├── monitoring.py            # 모니터링 전용 설정 (settings.py에서 re-export)
├── pipeline.json            # 파이프라인 런타임 설정 (대시보드에서 편집 가능)
├── layout.json              # 렌더러 레이아웃 SST (Single Source of Truth)
├── scene_policy.json        # 씬 타입별 mood/BGM/자막 정책
├── video_styles.json        # mood별 비디오 시각 스타일
├── feedback_config.json     # 성과 분석 → LLM 프롬프트 주입용 (자동 생성)
├── ab_tests.json            # A/B 테스트 설정
└── credentials.json         # 플랫폼 OAuth 토큰 (gitignore)

env/
└── .env                     # 환경변수 (gitignore)
```

---

## config/settings.py 주요 변수

### AI Worker

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `AI_POLL_INTERVAL` | `10` | APPROVED 게시글 폴링 간격 (초) |
| `CUDA_CONCURRENCY` | `1` | CUDA 세마포어 동시성 (TTS+VIDEO 병렬 시 2) |
| `MAX_RETRY_COUNT` | `3` | 파이프라인 최대 재시도 횟수 |
| `LLM_WORKER_URL` | `http://llm-worker:8090` | LLM 게이트웨이 주소 |
| `DEFAULT_LLM_MODEL` | `haiku` | 기본 LLM 모델 별칭 |
| `MEDIA_DIR` | `assets/media` | 미디어 파일 루트 |
| `ASSETS_DIR` | `assets/` | 에셋 루트 |

### TTS 설정

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `FISH_SPEECH_URL` | `http://fish-speech:8080` | Fish Speech API |
| `FISH_SPEECH_TIMEOUT` | `120` | TTS 요청 타임아웃 (초) |
| `FISH_SPEECH_TEMPERATURE` | `0.5` | 생성 다양성 (0.7→0.5, 중국어 회귀 방지) |
| `FISH_SPEECH_REPETITION_PENALTY` | `1.3` | 반복 억제 |
| `TTS_OUTPUT_FORMAT` | `wav` | 출력 포맷 |
| `TTS_SAMPLE_RATE` | `44100` | 샘플레이트 |

**VOICE_PRESETS (voice_key → assets/voices/ 파일명):**
| voice_key | 파일명 | 설명 |
|-----------|--------|------|
| `default` | `korean_man_default.wav` | 기본 남성 내레이터 |
| `anna` | `voice_preview_anna.mp3` | 여, 친근한 내레이션 |
| `yura` | `voice_preview_yura.mp3` | 여, 활기찬 대화체 (기본 TTS 보이스) |
| `han` | `voice_preview_han.mp3` | 남, 자연스러운 대화체 |
| `krys` | `voice_preview_krys.mp3` | 여, 뉴스/정보 전달형 |
| `sunny` | `voice_preview_sunny.mp3` | 여, 따뜻한 내레이션 |
| `yohan` | `voice_preview_yohan.mp3` | 남, 깊이 있는 내레이션 |
| `manbo` | `voice_preview_manbo.mp3` | 여, 유쾌한 대화체 |

### 비디오 설정 (LTX-2)

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `COMFYUI_URL` | `http://comfyui:8188` | ComfyUI API |
| `VIDEO_GEN_ENABLED` | `false` | Phase 4.5~7 활성화 여부 |
| `VIDEO_WORKFLOW_MODE` | `distilled` | `distilled`=8-step 빠른 생성, `full`=20-step 고품질 |
| `VIDEO_GEN_TIMEOUT` | `1200` | 비디오 생성 타임아웃 (초, 20분) |
| `VIDEO_RESOLUTION` | `(1280, 720)` | 기본 해상도 |
| `VIDEO_RESOLUTION_FALLBACK` | `(768, 512)` | 폴백 해상도 |
| `VIDEO_NUM_FRAMES` | `97` | 기본 프레임 수 (1+8×12) |
| `VIDEO_NUM_FRAMES_FALLBACK` | `65` | 폴백 프레임 수 (1+8×8) |
| `VIDEO_FPS` | `24` | 프레임레이트 |
| `VIDEO_STEPS` | `20` | Full 모델 denoising steps |
| `VIDEO_STEPS_DISTILLED` | `8` | Distilled 모델 steps |
| `VIDEO_CFG` | `3.5` | Classifier-free guidance (Full) |
| `VIDEO_CFG_DISTILLED` | `1.0` | CFG (Distilled, ManualSigmas 사용) |
| `VIDEO_I2V_THRESHOLD` | `0.6` | Image-to-Video 전환 임계값 |
| `VIDEO_MAX_RETRY` | `4` | 씬당 최대 재시도 (4단계 폴백) |
| `VIDEO_MAX_CLIPS_PER_POST` | `8` | 글당 최대 클립 수 |

**LTX-2 모델 파일** (`checkpoints/` 하위, HF 소스: `Kijai/LTXV2_comfy`):

| 파일 | 경로 | 용도 |
|------|------|------|
| `ltx-2-19b-distilled_Q4_K_M.gguf` | `diffusion_models/` | GGUF Q4 UNet (12.7GB, VRAM) |
| `ltx-2-19b-embeddings_connector_distill_bf16.safetensors` | `ltx-2/` | 텍스트 connector (2.9GB) |
| `LTX2_video_vae_bf16.safetensors` | `vae/` | VAE 디코더 (2.4GB) |
| `gemma-3-12b-it-qat-q4_0-unquantized/` | `text_encoders/` | Gemma-3 12B (15GB, CPU) |

> `ltxv_path`에 27GB FP8 full checkpoint 대신 2.9GB connector 파일 사용.
> `full` 모드 워크플로우(`t2v_ltx2.json`, `i2v_ltx2.json`)는 별도 FP8 모델 필요.

### 레이아웃 제약 (layout.json에서 로드)

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `MAX_TITLE_CHARS` | `40` | 썸네일 제목 최대 글자 수 |
| `MAX_HOOK_CHARS` | `50` | 후킹 문장 최대 글자 수 |
| `MAX_BODY_CHARS` | `45` | 본문 한 줄 최대 글자 수 |
| `MAX_CAPTION_CHARS` | `60` | 이미지 캡션 최대 글자 수 |

---

## config/pipeline.json

대시보드 설정 탭에서 편집. `load_pipeline_config()`로 로드 (5초 캐싱).

```json
{
  "tts_engine": "fish-speech",
  "tts_voice": "yura",
  "llm_backend": "cli",
  "llm_model": "haiku",
  "llm_model_overrides": {},
  "llm_api_base_url": "https://api.anthropic.com",
  "video_resolution": "1080x1920",
  "video_codec": "h264_nvenc",
  "bgm_volume": "0.15",
  "subtitle_font": "NanumGothic",
  "upload_platforms": ["youtube"],
  "upload_privacy": "unlisted",
  "auto_approve_enabled": "false",
  "auto_approve_threshold": "80",
  "use_content_processor": "false",
  "auto_upload": "false"
}
```

**llm_model_overrides 예시:**
```json
{
  "llm_model_overrides": {
    "chunk": "sonnet",
    "video_prompt": "sonnet"
  }
}
```

---

## config/scene_policy.json

씬 타입별 mood 매핑, BGM 카테고리, 자막 프리셋 정의.

```json
{
  "mood_policies": {
    "humor":       {"bgm_category": "humor",       "subtitle_preset": "casual"},
    "touching":    {"bgm_category": "touching",    "subtitle_preset": "dramatic"},
    "anger":       {"bgm_category": "anger",       "subtitle_preset": "news"},
    "sadness":     {"bgm_category": "sadness",     "subtitle_preset": "dramatic"},
    "horror":      {"bgm_category": "horror",      "subtitle_preset": "dramatic"},
    "info":        {"bgm_category": "info",        "subtitle_preset": "news"},
    "controversy": {"bgm_category": "controversy", "subtitle_preset": "news"},
    "daily":       {"bgm_category": "daily",       "subtitle_preset": "casual"},
    "shock":       {"bgm_category": "shock",       "subtitle_preset": "dramatic"}
  }
}
```

**자막 프리셋 4종:** `dramatic`, `casual`, `news`, `comment`

**BGM 경로:** `assets/bgm/{mood_category}/` (9개 폴더)

---

## config/layout.json

렌더러 레이아웃 Single Source of Truth. `settings.py`에서 로드해 `CONSTRAINTS` dict로 공개.

```json
{
  "constraints": {
    "post_title":         {"max_chars": 40},
    "hook_text":          {"max_chars": 50},
    "body_sentence":      {"max_chars": 45},
    "image_text_caption": {"max_chars": 60}
  },
  "canvas": {
    "width": 1080,
    "height": 1920,
    "fps": 30
  }
}
```

---

## config/video_styles.json

mood별 비디오 시각 스타일. Phase 6 영어 프롬프트 생성에 적용.

---

## 환경변수 (.env)

Docker Compose가 `env/.env`에서 읽음. Python은 `settings.py`에서 `load_dotenv()`.

**핵심 변수:**
```bash
# 데이터베이스
MARIADB_ROOT_PASSWORD=wagglebot_root
MARIADB_PASSWORD=wagglebot

# LLM 백엔드 선택 (cli | api)
LLM_BACKEND=cli                            # cli=llm-worker CLI 게이트웨이, api=Anthropic API 직접

# CLI 백엔드 인증 (llm-worker)
CLAUDE_HOST_CONFIG_DIR=/home/justant/.claude

# API 백엔드 인증 (LLM_BACKEND=api 시 사용. 없으면 credentials.json의 anthropic_api_key)
ANTHROPIC_API_KEY=sk-ant-...

# AI Worker
VIDEO_GEN_ENABLED=false
TTS_ENGINE=fish-speech
TTS_VOICE=yura
LLM_MODEL=haiku

# Telegram
TELEGRAM_BOT_TOKEN=...
ALLOWED_USER_IDS=...

# 알림
SLACK_WEBHOOK_URL=
EMAIL_ALERTS_ENABLED=false
```

---

## 도메인별 settings.yaml (ai_worker 서브모듈)

각 ai_worker 도메인 하위에 `settings.yaml` 선택적 배치 가능. `get_domain_setting()` 으로 조회.

```python
# 예시: ai_worker/core/settings.yaml의 retry.max_attempts
from config.settings import get_domain_setting
max_attempts = get_domain_setting("core", "retry", "max_attempts", default=3)
```

**도메인:** `core`, `script`, `scene`, `tts`, `video`, `renderer`
