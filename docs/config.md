# WaggleBot — 설정 레퍼런스

> **last-verified:** 2026-06-13
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
| `FISH_SPEECH_URL` | `http://fish-speech:8080` | OpenAudio S1 API (호스트 매핑 포트는 **8082**) |
| `FISH_SPEECH_TIMEOUT` | `300` | TTS 요청 타임아웃 (초) |
| `FISH_SPEECH_TEMPERATURE` | `0.8` | 생성 다양성 (S1 기본값, ADR-0005) |
| `FISH_SPEECH_TOP_P` | `0.8` | nucleus sampling |
| `FISH_SPEECH_REPETITION_PENALTY` | `1.1` | 반복 억제 |
| `FISH_SPEECH_NORMALIZE` | `False` | 서버 정규화 비활성 (자체 한국어 정규화 사용) |
| `FISH_SPEECH_USE_MEMORY_CACHE` | `"on"` | reference_id 인코딩 캐시 |
| `FISH_SPEECH_CHUNK_LENGTH` | `200` | 서버 청크 길이 |
| `TTS_OUTPUT_FORMAT` / `TTS_SAMPLE_RATE` | `wav` / `44100` | 출력 포맷·샘플레이트 |
| `TTS_SPEED` | `1.2` | 후처리 배속 (피치 보존). voices.json params로 per-voice 오버라이드 |
| `TTS_LOUDNORM_ENABLED` / `_PARAMS` | `True` / `I=-16:TP=-1.5:LRA=11` | EBU R128 음량 정규화 (후 aresample 44100 — concat 호환) |
| `TTS_MAX_CHARS_PER_REQUEST` | `150` | 초과 시 문장 경계 분할·병합 |
| `TTS_MAX/MIN_SECS_PER_CHAR` | `0.35` / `0.05` | 길이 검증 상·하한 (비한국어/잘림 감지) |
| `TTS_EMOTION_ENABLED` | `True` | tts_emotion → 감정 마커 주입 |
| `TTS_LAUGH_MARKER_ENABLED` | `False` | ㅋㅋ→(laughing) (실험적) |
| `TTS_SHORT_TEXT_PADDING` | `False` | 짧은 텍스트 패딩 (S1+참조에선 불필요) |
| `WHISPER_MODEL` / `_DEVICE` / `_COMPUTE_TYPE` | `large-v3` / `cpu` / `int8` | prepare_voice 전사 (CPU, VRAM 무경합) |

> `KOREAN_CHARS_PER_SEC=4.0`은 speed 1.2 가정값 — per-voice `speed` 오버라이드는
> `estimate_tts_duration`/클립 길이 추정을 왜곡하므로 신중히 사용.

**TTS_EMOTION_MARKERS (tts_emotion → S1 마커):**
gentle→`(soft tone)`, cheerful→`(joyful)`, serious→`(serious)`, sad→`(sad)`,
whispering→`(whispering)`, neutral→`""`, friendly→`(relaxed)`, surprised→`(surprised)`.
⚠ 씬타입 키의 `EMOTION_TAGS`와는 다른 축.

**VOICE_PRESETS (voices.json v2): `{key: {label, ref_dir, file, params}}`**
- `ref_dir`: `assets/voices/<key>/` 폴더 (NN.wav+NN.lab) = fish-speech `reference_id`
- `file`: 대시보드 sampleUrl(`/api/media/voices/<file>`)·base64 폴백 경로 (`<key>/01.wav`)
- `params`: per-voice 오버라이드 `{temperature, top_p, speed}` (없으면 전역 기본값)
- 등록/갱신: `python -m tools.prepare_voice --input <녹음> --key <키> --label <라벨>`
- 키: default, anna, han, krys, yohan, yura, manbo

### 비디오 설정 (LTX-2)

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `COMFYUI_URL` | `http://comfyui:8188` | ComfyUI API |
| `VIDEO_GEN_ENABLED` | `false` | Phase 4.5~7 활성화 여부 |
| `VIDEO_WORKFLOW_MODE` | `distilled` | `distilled`=8-step 빠른 생성, `full`=20-step 고품질 |
| `VIDEO_GEN_TIMEOUT` | `1200` | 비디오 생성 타임아웃 (초, 20분) |
| `VIDEO_RESOLUTION` | `(1280, 720)` | 기본 해상도 |
| `VIDEO_RESOLUTION_FALLBACK` | `(768, 512)` | 폴백 해상도 |
| `VIDEO_NUM_FRAMES` | `97` | 기본 프레임 수 (1+8×12, estimated_tts_sec 없을 때) |
| `VIDEO_NUM_FRAMES_FALLBACK` | `65` | 폴백 프레임 수 (1+8×8) |
| `VIDEO_NUM_FRAMES_MAX` | `145` | 동적 프레임 상한 (1+8×18 = 6.04초 @24fps) → [ADR-0004](adr/0004-clip-4-6s-frames-145.md) |
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

### 모니터링 설정 (config/monitoring.py에서 re-export)

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `MONITORING_ENABLED` | `true` | 모니터링 데몬 활성화 여부 |
| `HEALTH_CHECK_INTERVAL` | `300` | 헬스 체크 주기 (초) |
| `GPU_TEMP_WARNING` | `75` | GPU 온도 경고 임계치 (°C) |
| `GPU_TEMP_CRITICAL` | `80` | GPU 온도 CRITICAL 임계치 → 이메일/슬랙 발송 |
| `GPU_VRAM_WARNING` | `85` | VRAM 사용률 경고 임계치 (%) — 누수 의심 로그 |
| `GPU_VRAM_CRITICAL` | `95` | VRAM 사용률 CRITICAL 임계치 → 이메일/슬랙 발송 |
| `DISK_USAGE_WARNING` | `80` | 디스크 사용률 경고 임계치 (%) |
| `DISK_USAGE_CRITICAL` | `90` | 디스크 사용률 CRITICAL 임계치 |
| `MEMORY_USAGE_WARNING` | `85` | RAM 사용률 경고 임계치 (%) |
| `MEMORY_USAGE_CRITICAL` | `95` | RAM 사용률 CRITICAL 임계치 |

### 크롤러 설정 (config/crawler.py에서 re-export)

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `ENABLED_CRAWLERS` | `nate_pann` | 활성화할 크롤러 목록 (쉼표 구분, `ENABLED_CRAWLERS` env) |
| `CRAWL_INTERVAL_HOURS` | `1` | 크롤 주기 (시간) |
| `CRAWL_DELAY_SECTION` | `(1.5, 4.0)` | 섹션 간 딜레이 범위 (초) |
| `CRAWL_DELAY_POST` | `(0.3, 1.2)` | 게시글 간 딜레이 범위 (초) |
| `CRAWL_DELAY_COMMENT` | `(0.2, 0.8)` | 댓글 간 딜레이 범위 (초) |
| `BLOCK_RETRY_MAX` | `2` | 차단 감지 시 최대 재시도 횟수 |
| `BLOCK_RETRY_BASE_DELAY` | `30.0` | 재시도 기본 대기 (초) |
| `BLOCK_RETRY_BACKOFF` | `2.0` | 지수 백오프 배수 |
| `BLOCK_RETRY_MAX_DELAY` | `300.0` | 재시도 최대 대기 상한 (초) |
| `REQUEST_TIMEOUT` | `15` | HTTP 요청 타임아웃 (초) |

### Telegram 크롤러 알림

| 변수 | env 키 | 기본값 | 설명 |
|------|--------|--------|------|
| `TELEGRAM_HOOK_URL` | `TELEGRAM_HOOK_URL` | `http://telegram-bridge:3847/hook` | telegram-bridge hook 엔드포인트 |
| `TELEGRAM_CRAWL_ALERT_ENABLED` | `TELEGRAM_CRAWL_ALERT` | `false` | 크롤러 Telegram 알림 활성화 여부 |
| `TELEGRAM_CRAWL_ALERT_THRESHOLD` | `TELEGRAM_ALERT_THRESHOLD` | `100` | 알림 발송 최소 점수 |

> 점수 ≥ `TELEGRAM_CRAWL_ALERT_THRESHOLD` 이거나 자동승인 게시글이면 hook에 `notification` 이벤트 POST.
> `TELEGRAM_CRAWL_ALERT=true`로 전환하고 `docker-compose.yml` crawler 서비스의 환경변수 3개 확인.

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

**llm_model_overrides 예시** (키는 실제 call_type — `transport.py`의 `_CALL_TYPE_MODEL_MAP` 참조):
```json
{
  "llm_model_overrides": {
    "chunk": "sonnet",
    "video_prompt_t2v": "sonnet",
    "video_prompt_i2v": "sonnet"
  }
}
```
비디오 관련 call_type: `video_prompt_t2v` · `video_prompt_i2v` · `video_prompt_simplify` · `video_visual_anchor` · `video_image_brief` (기본 전부 haiku)

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
    "post_title":         {"max_chars": 40, "max_lines": 1},
    "hook_text":          {"max_chars": 40, "max_lines": 2},
    "body_sentence":      {"max_chars": 20, "max_lines": 1},
    "image_text_caption": {"max_chars": 40, "max_lines": 2},
    "comment_line":       {"max_chars": 60, "max_lines": 3},
    "body_line":          {"max_chars": 40, "max_lines": 2}
  },
  "canvas": {
    "width": 1080,
    "height": 1920
  },
  "global": {
    "header": {
      "height": 150,
      "bg_color": "#FBD024",
      "ink_color": "#1A1A1A",
      "channel_name": "와글",
      "title_font_size": 52,
      "icon_stroke": 6
    },
    "title_block": {
      "pad_top": 32, "pad_x": 44,
      "font_size": 50, "color": "#161616", "weight": "bold",
      "line_height": 62, "max_lines": 2,
      "meta": {"gap_top": 16, "font_size": 28, "color": "#9C9C9C"},
      "divider": {"gap_top": 20, "thickness": 2, "color": "#E7E7E7"}
    },
    "content": {"gap_top": 28}
  },
  "scenes": {
    "intro": {},
    "image_text": {},
    "text_only": {},
    "image_only": {},
    "video_text": {},
    "comments": {
      "description": "커뮤니티 댓글 리스트 — 아바타·닉네임·BEST·추천수",
      "dwell_sec": 4.0
    },
    "outro": {
      "description": "댓글 참여 유도 — 마스코트 + 질문 + 입력창 목업 (구독유도 없음)"
    }
  }
}
```

**`global` 주요 필드:**

| 키 | 설명 |
|----|------|
| `global.header.height` | 헤더 높이 (px) — 구버전 `header_height` 대체 |
| `global.header.bg_color` | 헤더 배경색 (`#FBD024`) — 구버전 `header_color` 대체 |
| `global.header.ink_color` | 헤더 텍스트·아이콘 색 (`#1A1A1A`) |
| `global.header.channel_name` | 헤더 채널명 표시 (`와글`) |
| `global.title_block` | 헤더 아래 게시글 제목 블록 레이아웃 (font_size, pad, meta, divider) |
| `global.content.gap_top` | title_block 아래 콘텐츠 영역 상단 여백 (px) |

> 구버전 `global.header_height` · `global.header_color` · `global.base_layout` · `global.header_title` 키는 제거됨. `_frames.py` 전면 재작성과 함께 반영.

**`scenes` 등록 씬 타입:** `intro` / `image_text` / `text_only` / `image_only` / `video_text` / **`comments`**(신규) / `outro`

---

## config/video_styles.json

mood 9종별 비디오 시각 스타일. Phase 6 영어 프롬프트(T2V) 생성 시 user prompt의
MOOD STYLING 블록에 주입된다.

**구조 계약** (mood당 4키 — `prompt_engine._get_style_block()`·테스트가 의존):

| 키 | 타입 | 용도 |
|----|------|------|
| `style_hint` | str | 시각 톤 (조명·프레이밍·텍스처) |
| `camera_hints` | list[str] | 카메라 무브 후보 — **젠틀 단일 무브 2~3개만** (LTX-2 CAMERA RULE) |
| `color_palette` | list[str] | 색감 방향 |
| `atmosphere` | str | 전체 분위기·페이싱 |

**작성 원칙 (V3):** 실사 촬영 가능한 단서만 허용. 편집 효과(freeze frame, speed ramp,
glitch, split-screen, strobing)·반실사 렌즈(fish-eye)·과격 무브(whip pan, crash zoom,
snap zoom)는 금지 — 템플릿의 REALISM 블록과 충돌해 AI 티를 유발한다.
(`test_prompt_engine.py::test_video_styles_no_anti_realism_cues`가 가드)

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
