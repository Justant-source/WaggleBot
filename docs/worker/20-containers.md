# WaggleBot — 설정 레퍼런스

> **last-verified:** 2026-11-27
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
| `STALE_PROCESSING_MINUTES` | `30` | 무활동 PROCESSING 고착 회수 기준(분). 워커 재시작 시는 즉시 회수 |
| `HEARTBEAT_INTERVAL_SEC` | `30` | 소유 중 post 하트비트 갱신 주기(초) |
| `STALE_SCAN_INTERVAL_SEC` | `60` | 고착 PROCESSING 점검 주기(초) |
| `PHASE_STALL_SEC` | `7200` | 같은 phase에서 진행 stamp가 이 시간 넘게 없으면 inflight 하트비트 갱신 중단(경고) |
| `LLM_WORKER_URL` | `http://llm-worker:8090` | LLM 게이트웨이 주소 |
| `DEFAULT_LLM_MODEL` | `haiku` | 기본 LLM 모델 별칭 |
| `MEDIA_DIR` | `assets/media` | 미디어 파일 루트 |
| `ASSETS_DIR` | `assets/` | 에셋 루트 |

### TTS 설정

TTS는 외부 **Local-TTS 제공자**(`http://local-tts:8500`, Supertonic)에 요청만 보낸다. WaggleBot은 합성 코드·게이트·GPU 임대·컨테이너 제어를 갖지 않는다([ADR-0006](../shared/90-adr/0006-local-tts-provider.md)). 서버 정규화·청크 분할·loudnorm(-16)·속도 적용은 서버가 하고, 앱은 `prenorm.py` 전처리만 한다([ADR-0008](../shared/90-adr/0008-tts-normalization-standard.md)). 아래 `TTS_SERVER_*`·`TTS_PROFILE`·`TTS_CLIENT_ID`·`TTS_SPEED`는 compose가 `ai_worker`와 `dashboard_worker`에 같은 값으로 전달한다(`env/.env.example` 참조).

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `TTS_SERVER_URL` | `http://local-tts:8500` | Local-TTS 주소(외부 네트워크 `local_tts_net` 별칭) |
| `TTS_SERVER_TOKEN` | `""` | 서버가 `LOCAL_TTS_TOKEN`을 요구할 때만 설정(`.env`에서만 읽음) |
| `TTS_SERVER_TIMEOUT_SEC` | `120` | 요청 1건 read 타임아웃(초) |
| `TTS_SERVER_RETRIES` | `3` | 첫 시도 이후 추가 재시도(연결 실패·429·503) |
| `TTS_SERVER_MAX_WAIT_SEC` | `3600` | job 완료·서버 준비 대기 상한(초). 소진 시 `TTSUnavailable` → APPROVED 재큐 |
| `TTS_PROFILE` | `wagglebot/shorts-ko` | 서버 발음 프로필(비우면 미사용). 원본 `config/tts_profile/shorts-ko.yaml` |
| `TTS_CLIENT_ID` | `wagglebot` | `X-Client-Id` = 프로필 네임스페이스(프로필 키 접두와 같아야 함) |
| `TTS_SPEED` | `1.1` | 서버 `speed` 옵션으로만 전달. 로컬 atempo 없음(이중 적용 금지). voices.json `params.speed` 오버라이드는 더 이상 합성에 쓰지 않는다 |
| `TTS_OUTPUT_FORMAT` / `TTS_SAMPLE_RATE` | `wav` / `44100` | 출력 포맷·샘플레이트 |
| `TTS_LOUDNORM_ENABLED` / `_PARAMS` | `True` / `I=-16:TP=-1.5:LRA=11` | 렌더러 최종 믹스 단계용(`renderer/_tts.py`). 합성 결과 1차 loudnorm(-16, TP -1.5)은 서버가 수행 |

고정값(코드 상수, `ai_worker/tts/synth.py`): 요청 옵션 `lang=ko`, `chunk={mode:max_chars, max_chars:120}`, `postprocess.loudnorm={i:-16, tp:-1.5}`, `output.format=wav`. 보이스는 `voice_resolver.resolve_voice()`가 항상 `M1~M5`·`F1~F5` 중 하나로 정한다.

**삭제된 설정(Fish 시절):** `FISH_SPEECH_*`, `ATOMIC_TTS_FISH_GATE_URL`, `FISH_GATE_*`, `FISH_LEASE_*`, `TTS_EMOTION_ENABLED`, `TTS_LAUGH_MARKER_ENABLED`, `TTS_SHORT_TEXT_PADDING`, `TTS_MAX_CHARS_PER_REQUEST`, `TTS_MAX/MIN_SECS_PER_CHAR`, `TTS_EMOTION_MARKERS`, `VOICE_REFERENCE_TEXTS`. 감정 마커·ㅋㅋ 웃음 마커·웜업·참조 음성·품질 재시도(`quality.py`)는 폐기됐다.

**디스크 TTS 캐시:** `processor.py`의 `_TTS_POST_PROCESS_CACHE_VERSION = "pp_v7"`, 키 `프리셋:텍스트:speed:pp_v7`. 캐시 키는 실제 해석된 프리셋(M1~F5) 기준이라, 구 `pp_v6`(Fish) WAV는 재사용되지 않는다.

| `WHISPER_MODEL` / `_DEVICE` / `_COMPUTE_TYPE` | `large-v3` / `cpu` / `int8` | faster-whisper 설정(CPU, VRAM 무경합). `prepare_voice.py`는 삭제됨 — 현재 렌더 타이밍 정렬은 아래 `TTS_ALIGNMENT_*` |
| `HF_HOME` / `HF_HUB_CACHE` / `HF_XET_CACHE` / `XDG_CACHE_HOME` | `assets/models/faster-whisper/huggingface/**` | settings import 시 writable `WHISPER_DOWNLOAD_ROOT` 하위로 강제. uid 1000 worker의 `/.cache` 권한 실패 방지 |
| `HF_HUB_DISABLE_XET` | `1` | Xet 별도 cache를 비활성화해 Hub HTTP download만 사용 |
| `TTS_ALIGNMENT_MODEL` / `_DEVICE` / `_COMPUTE_TYPE` | `small` / `cpu` / `int8` | 통합 내레이터 WAV의 줄별 실제 발화 시각을 구하는 faster-whisper 정렬 |
| `TTS_ALIGNMENT_MIN_CONFIDENCE` | `0.55` | 원문↔전사 문자 정렬 신뢰도 하한. 미달/실패 시 장면별 TTS 폴백 |
| `TTS_TEXT_LEAD_SEC` | `0.15` | 각 일반 텍스트 줄이 해당 음성보다 먼저 보이는 시간. 첫 WAV는 PCM 선행 무음을 측정해 부족분만 prepend |
| `TTS_OUTRO_PRE_PAUSE_SEC` / `_TEXT_LEAD_SEC` / `_TAIL_SEC` | `0.25` / `0.15` / `0.50` | 마지막 댓글 뒤 휴지, 클로징 텍스트 선행, 클로징 발화 뒤 여백 |

> `KOREAN_CHARS_PER_SEC=4.0`은 speed 1.1 가정값 — per-voice `speed` 오버라이드는
> `estimate_tts_duration`/클립 길이 추정을 왜곡하므로 신중히 사용.

**VOICE_PRESETS (voices.json v4): `{key: {label, gender, engine}}`**
- 키 10종: 남 `M1~M5`, 여 `F1~F5` (Supertonic 프리셋, `engine: supertonic`). 정본 = `config/voices.json`
- 합성 보이스 결정은 `ai_worker/tts/voice_resolver.py`: 프리셋 키는 그대로, 구 키(`seohyeon_ref`·`kangil_ref`·`yura` 등 Fish 참조 음성 키)는 **성별 보존**으로 `random.Random(post_id)` 순열에서 구 키 서수로 매핑, `None`·빈 값·미지 키는 post_id 시드 결정적 랜덤(post_id도 없으면 `F1`). 단 `default`는 구 키 목록의 **남성 4번째 서수**라 성별 보존 규칙에 따라 남성 프리셋(M1~M5 순열 중 하나)으로 해석된다 → [ADR-0007](../shared/90-adr/0007-voice-presets.md)
- 샘플: `assets/voices/voice_preview_<KEY>.mp3`(사전 생성, backend `/api/tts/voices/{key}/sample`)
- `ref_dir`·`file`·`params(temperature/top_p/speed)`·`age_range`는 `settings.VOICE_PRESETS` 로더가 읽지만 v4 항목에는 없으며 합성에 쓰지 않는다(레거시 필드)
- 기본값: `pipeline.json` `tts_engine=local-tts`, `tts_voice=default`(→ 남성 프리셋, post_id별 결정적), `comment_voices=["M2","F2","M3"]`, `scene/settings.yaml` `comment_voice_mapping`: author `M2` · partner `F2` · neutral `default`
- 등록·갱신 도구(`prepare_voice.py`)는 삭제됨. 발음 프로필 동기화는 `worker/tools/sync_tts_profile.py`(`--dry-run`·업로드·`--activate`)

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
| `VIDEO_NUM_FRAMES_MAX` | `145` | 동적 프레임 상한 (1+8×18 = 6.04초 @24fps) → [ADR-0004](../shared/90-adr/0004-clip-4-6s-frames-145.md) |
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

### Telegram → ASM 마케팅 콜백 forwarder

| 변수 | env 키 | 기본값 | 설명 |
|------|--------|--------|------|
| `config.asm.callbackUrl` | `ASM_TELEGRAM_CALLBACK_URL` | `http://100.115.252.61:8200/api/v1/telegram/callback` | ASM(Again-Spring-Marketing) 콜백 수신 엔드포인트 (Tailscale) |
| `config.asm.bearerToken` | `ASM_BEARER_TOKEN` | (빈 문자열) | ASM 콜백 요청 인증 토큰 |
> `redrive:`/`ignore:` 접두사 `callback_query`만 이 URL로 raw `data` 문자열째 전달(필드 수·형식 미해석).
> ASM이 idempotency·만료·legacy(4-field) 거부·`answerCallbackQuery`·후속 메시지를 전부 소유 — telegram-bridge는 순수 forwarder.
> ASM 연결 실패(non-2xx·타임아웃) 시에만 브리지가 폴백으로 `answerCallbackQuery` 응답(버튼 무한 로딩 방지).

---

## config/pipeline.json

대시보드 설정 탭에서 편집. `load_pipeline_config()`로 로드 (5초 캐싱). 아래는 구조 예시이며, 실제 현재값은 `config/pipeline.json`이 정본이다.

```json
{
  "tts_engine": "local-tts",
  "tts_voice": "default",
  "llm_backend": "api",
  "llm_model": "haiku",
  "llm_model_overrides": {},
  "llm_api_base_url": "https://api.clcocloud.com/claude/v1",
  "llm_prompt_cache": "true",
  "llm_cache_ttl": "5m",
  "comment_voices": "[\"M2\", \"F2\", \"M3\"]",
  "video_resolution": "1080x1920",
  "video_codec": "h264_nvenc",
  "bgm_volume": "0.15",
  "subtitle_font": "NanumGothic",
  "upload_platforms": ["youtube"],
  "upload_privacy": "unlisted",
  "auto_approve_enabled": "false",
  "auto_approve_threshold": "80",
  "use_content_processor": "true",
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
TTS_ENGINE=local-tts
TTS_VOICE=default

# TTS (Local-TTS 제공자)
TTS_SERVER_URL=http://local-tts:8500
TTS_SERVER_TOKEN=
TTS_SERVER_TIMEOUT_SEC=120
TTS_SERVER_RETRIES=3
TTS_SERVER_MAX_WAIT_SEC=3600
TTS_PROFILE=wagglebot/shorts-ko
TTS_CLIENT_ID=wagglebot
TTS_SPEED=1.1
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
