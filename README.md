# WaggleBot

> 커뮤니티 인기 게시글을 자동으로 수집하여 유튜브 쇼츠 영상으로 변환하는 AI 파이프라인

[![Python](https://img.shields.io/badge/Python-3.12-blue.svg)](https://www.python.org/)
[![Spring Boot](https://img.shields.io/badge/Spring%20Boot-3.3-6DB33F.svg)](https://spring.io/)
[![Next.js](https://img.shields.io/badge/Next.js-14-000000.svg)](https://nextjs.org/)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED.svg)](https://www.docker.com/)
[![GPU](https://img.shields.io/badge/GPU-NVIDIA%20RTX%203090-76B900.svg)](https://www.nvidia.com/)

---

## 프로젝트 개요

커뮤니티 게시글을 크롤링하고, **Claude LLM**으로 쇼츠 대본을 생성한 뒤, TTS·LTX-2 비디오·FFmpeg로 9:16 영상을 자동 생성하여 YouTube에 업로드하는 완전 자동화 시스템.

### 주요 기능

- **자동 크롤링**: 네이트판·뽐뿌·DC인사이드·FM코리아 인기 게시글 수집 + 시간감쇠 인기도 스코어링
- **AI 대본**: Claude(haiku/sonnet/opus) 기반 8-Phase 파이프라인 — 의미 단위 청킹 → 씬 배분 → 감정 태그
- **TTS**: Fish Speech 1.5 (zero-shot 음성 클로닝, 감정 태그 지원)
- **Mood 기반 씬 연출**: 9가지 감성 톤(humor/touching/horror 등) 프리셋 → 비주얼·BGM·TTS 감정 자동 배분
- **비디오 생성**: LTX-2 19B (ComfyUI, T2V/I2V, 720p) — `VIDEO_GEN_ENABLED=true`일 때 활성
- **영상 렌더링**: FFmpeg + NVENC GPU 가속, ASS 동적 자막, 정적+비디오 하이브리드 합성, 썸네일 자동 생성
- **대시보드**: Next.js 14 어드민 UI(수신함/편집실/갤러리/분석/설정/LLM 로그/진행상황) + Spring Boot REST API
- **자동 업로드**: YouTube Shorts + YouTube Analytics 성과 추적 → LLM 피드백 루프
- **텔레그램 브리지**: 모바일에서 작업 승인/모니터링 (선택)

### 시스템 플로우

```
크롤링 → 스코어링 → 수신함 검수 → 편집실(대본수정/TTS미리듣기)
→ AI워커(8-Phase: 청킹 → 씬 배분 → TTS → 비디오 → 렌더링 → 썸네일)
→ 갤러리 → YouTube 업로드 → 성과 분석 → LLM 피드백
```

### 8-Phase 파이프라인

```
Phase 1   analyze_resources    이미지:텍스트 비율 분석 (ResourceProfile)
Phase 2   chunk_with_llm       LLM 의미 단위 청킹 (raw script)
Phase 3   validate_and_fix     max_chars 검증 + 한국어 분할
Phase 4   SceneDirector        씬 배분 + 감정 태그 (list[SceneDecision])
Phase 4.5 assign_video_modes   씬별 t2v/i2v 모드 할당
Phase 5   TTS 생성             Fish Speech (scene.text_lines)
Phase 6   video_prompt 생성    한국어 → 영어 프롬프트
Phase 7   video_clip 생성      ComfyUI LTX-2 클립
Phase 8   FFmpeg 렌더링        최종 9:16 영상 + 썸네일
```

> Phase 4.5~7은 `VIDEO_GEN_ENABLED=true`일 때만 실행됩니다.

### 기술 스택

| 분류 | 기술 |
|------|------|
| 워커 | Python 3.12 (크롤러 · 8-Phase AI 파이프라인 · 업로더 · 분석 · 모니터링) |
| LLM | **Claude** — `haiku` / `sonnet` / `opus`, call_type별 자동 라우팅 |
| LLM 백엔드 | **CLI**(llm-worker Spring Boot 게이트웨이 + `claude` CLI, 구독 인증) 또는 **API**(Anthropic API, `ANTHROPIC_API_KEY`) — 대시보드에서 전환 |
| TTS | Fish Speech 1.5 (zero-shot 클로닝, `fishaudio/fish-speech:v1.5.1`) |
| 비디오 | LTX-2 19B (ComfyUI, T2V/I2V, 720p) — GGUF Q4 UNet + Gemma 3 텍스트 인코더 |
| DB | MariaDB 11 + SQLAlchemy ORM(Python) + Flyway 마이그레이션(backend) |
| 영상 | FFmpeg (`h264_nvenc` GPU 가속) |
| 백엔드 | Spring Boot 3.3 (Java) REST API |
| 프론트 | Next.js 14 + TypeScript 어드민 대시보드 |
| 인프라 | Docker Compose (RTX 3090 24GB GPU) |

> **Ollama / qwen2.5는 더 이상 사용하지 않습니다.** 모든 LLM 호출은 `worker/ai_worker/llm/transport.py`의 `call_llm()`을 통해 Claude(CLI 또는 API)로 라우팅됩니다.

---

## 설치 가이드

**RTX 3090 24GB 이상** NVIDIA GPU 환경을 지원합니다. GPU 환경 설정: [docs/arch/env/ENV_GPU.md](docs/arch/env/ENV_GPU.md)

### 1. WSL2 + Ubuntu 설치

```powershell
# PowerShell (관리자 권한)
wsl --install -d Ubuntu-24.04
```

### 2. Docker + NVIDIA Container Toolkit

```bash
# Docker 설치
sudo apt-get update && sudo apt-get install -y ca-certificates curl gnupg
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update && sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
sudo usermod -aG docker $USER && newgrp docker

# NVIDIA Container Toolkit (자동)
bash scripts/setup_docker_gpu.sh
```

### 3. Claude LLM 백엔드 설정

LLM 백엔드는 두 가지 중 하나를 선택합니다 (대시보드 설정 또는 `.env`의 `LLM_BACKEND`로 전환).

**(A) CLI 백엔드 — 기본값.** `llm-worker` 컨테이너가 호스트의 `~/.claude` 인증을 마운트해 `claude` CLI를 subprocess로 호출합니다 (Claude 구독 사용, 추가 API 과금 없음).

```bash
# 호스트에 Claude Code(CLI) 설치 후 1회 로그인 → ~/.claude 생성
claude   # 로그인 진행

# .env 에서 마운트 경로 지정 (기본: /home/<user>/.claude)
# CLAUDE_HOST_CONFIG_DIR=/home/justant/.claude
```

**(B) API 백엔드.** Anthropic API를 직접 호출합니다.

```bash
# .env 에 키 입력 (또는 config/credentials.json 의 anthropic_api_key)
# ANTHROPIC_API_KEY=sk-ant-...
# LLM_BACKEND=api
```

> 모델 라우팅: `chunk`/`generate_script`/`scene_director`/`feedback` → **sonnet**,
> `video_prompt`/`translate`/`comment_summarize` → **haiku**.
> `config/pipeline.json`의 `llm_model_overrides`로 call_type별 override 가능합니다.

### 4. Fish Speech 모델 다운로드

```bash
pip install huggingface_hub          # 없는 경우
bash scripts/download_fish_speech.sh # 모델 다운로드 (~1.4GB)
```

다운로드 후 구조 확인:
```
checkpoints/fish-speech-1.5/
├── model.pth
├── firefly-gan-vq-fsq-8x1024-21hz-generator.pth
└── (기타 config 파일)
```

### 5. LTX-2 모델 다운로드 (비디오 생성 사용 시)

```bash
# LTX-2 19B 모델 + Gemma 3 텍스트 인코더 + 업스케일러 (~20GB+)
bash scripts/download_ltx2.sh
```

다운로드 후 구조 확인:
```
checkpoints/
├── ltx-2/                                   ← 메인 + Distilled 체크포인트
├── text_encoders/                           ← Gemma 3 12B 텍스트 인코더
├── latent_upscale_models/                   ← Spatial/Temporal 업스케일러
├── loras/                                    ← Distilled LoRA
├── diffusion_models/  vae/                   ← GGUF UNet / VAE
```

### 6. 참조 오디오 준비

Fish Speech는 **zero-shot 음성 클로닝** 방식입니다. 원하는 목소리의 WAV 파일을 준비하세요.

```
assets/voices/
└── korean_man_default.wav   ← 10~30초, 16kHz 이상, 깨끗한 음성
```

참조 텍스트를 `config/settings.py`의 `VOICE_REFERENCE_TEXTS`에 등록:
```python
VOICE_REFERENCE_TEXTS = {
    "default": "WAV 파일에서 실제로 말한 내용을 입력하세요.",
}
```

### 7. 환경 변수 설정 및 실행

Docker Compose 정의와 환경 변수는 모두 `env/` 디렉터리에 있습니다.

```bash
git clone https://github.com/justant/WaggleBot.git
cd WaggleBot

# 환경 변수 설정
cp env/.env.example env/.env
nano env/.env
#   MARIADB_ROOT_PASSWORD=...
#   MARIADB_PASSWORD=...
#   LLM_BACKEND=cli            # 또는 api
#   CLAUDE_HOST_CONFIG_DIR=/home/<user>/.claude   # CLI 백엔드
#   ANTHROPIC_API_KEY=sk-ant-...                   # API 백엔드
#   VIDEO_GEN_ENABLED=false    # 비디오 생성 토글

# 실행 (compose 파일이 env/ 에 있으므로 -f 로 지정)
docker compose -f env/docker-compose.yml up -d
docker compose -f env/docker-compose.yml ps
```

대시보드(어드민): **http://localhost:3000/admin** &nbsp;·&nbsp; 백엔드 API: **http://localhost:8080**

### 8. DB 스키마

DB 스키마는 **Spring Boot backend가 기동 시 Flyway 마이그레이션을 자동 적용**합니다
(`backend/src/main/resources/db/migration/` — `V1__jobs_table.sql`, `V2__base_schema.sql` …).
별도의 수동 초기화 단계는 필요하지 않습니다.

생성되는 주요 테이블: `posts`, `comments`, `contents`, `jobs`, `llm_logs`.

---

## 사용법

### 대시보드 구성 (`/admin`)

| 페이지 | 역할 |
|----|------|
| **수신함** (inbox) | 크롤링된 게시글 스코어 기반 추천 → 배치 승인/거절 |
| **편집실** (editor) | AI 대본 미리보기/수정, TTS 미리듣기, 제목·태그 편집 |
| **갤러리** (gallery) | 저해상도 프리뷰 → 고화질 렌더링 → 업로드 스케줄링 |
| **분석** (analytics) | YouTube 성과(조회수/유지율), 생산성 지표, AI 인사이트 |
| **설정** (settings) | 파이프라인 설정, LLM 백엔드·모델, 자동 승인 임계값, 자막 스타일 |
| **LLM 로그** (llm-logs) | LLM 호출 이력/응답 추적 |
| **진행상황** (progress) | 파이프라인 실시간 처리 단계 모니터링 |

### 영상 생성 흐름

```
수신함 승인 → 편집실(대본 수정)
→ Phase 1~4: Claude 대본/씬 생성(sonnet, llm-worker 또는 API)
→ Phase 5: Fish Speech TTS(~10초) → VRAM 해제
→ Phase 6~7: LTX-2 비디오 클립 생성(ComfyUI, 씬당 1~3분) → VRAM 해제
→ Phase 8: FFmpeg 하이브리드 렌더링(정적+비디오 합성) → 썸네일 생성
→ 갤러리 확인 → 업로드
```

### TTS 음성 변경

`config/settings.py`의 `VOICE_PRESETS`에 WAV 파일 추가 후 등록:
```python
VOICE_PRESETS = {
    "default":  "korean_man_default.wav",
    "female":   "korean_female.wav",    # 추가 예시
}
VOICE_REFERENCE_TEXTS = {
    "default": "기존 참조 텍스트",
    "female":  "female 파일에서 실제 말한 내용",
}
```

---

## Docker 서비스 구성

| 서비스 | 역할 | 포트 (host:container) |
|--------|------|------|
| `db` | MariaDB 11 | 3306:3306 |
| `crawler` | 크롤링 루프 (`python main.py`) | — |
| `fish-speech` | TTS (zero-shot 클로닝) | 8082:8080 |
| `comfyui` | LTX-2 비디오 생성 | 8188:8188 |
| `ai_worker` | 8-Phase 파이프라인 (`ai_worker.core.main`) | — |
| `monitoring` | 헬스체크/알림 데몬 | — |
| `llm-worker` | Claude CLI 게이트웨이 (Spring Boot) | 8090:8090 |
| `backend` | Spring Boot 3.3 REST API | 8080:8080 |
| `frontend` | Next.js 14 대시보드 | 3000:3000 |
| `dashboard_worker` | `jobs` 테이블 폴링 실행 데몬 | — |
| `telegram-bridge` | 텔레그램 봇 브리지 (선택) | 3847:3847 |

> `dashboard_worker`는 Java backend가 `jobs` 테이블에 enqueue한 작업을 Python이 폴링·실행합니다.
> `llm-worker`는 `POST :8090/v1/invoke`로 호출되는 `claude` CLI subprocess 게이트웨이입니다
> (소스: `worker/llm/`, `~/.claude` 마운트 인증).

---

## 프로젝트 구조

```
WaggleBot/
├── CLAUDE.md                          # AI 개발 규칙 (코딩 컨벤션, 하드 제약)
├── README.md
├── env/                               # ★ Docker Compose 단위
│   ├── docker-compose.yml             # 11개 서비스 정의 (RTX 3090 GPU)
│   ├── .env / .env.example
│   └── Dockerfile.comfyui             # ComfyUI 이미지 (CUDA, LTX-2 노드)
├── backend/                           # Spring Boot 3.3 REST API (Java)
│   └── src/main/
│       ├── java/com/wagglebot/
│       │   ├── controller/            # Inbox/Editor/Gallery/Analytics/Settings/Progress/LlmLog/Media
│       │   ├── domain/  job/  settings/  config/  common/  exception/
│       └── resources/db/migration/    # Flyway (V1__jobs_table, V2__base_schema, …)
├── frontend/                          # Next.js 14 어드민 대시보드 (TypeScript)
│   ├── app/(admin)/admin/             # inbox / editor / gallery / analytics / settings / llm-logs / progress
│   └── lib/                           # types, API 클라이언트
├── worker/                            # Python 워커 모노레포
│   ├── Dockerfile                     # 통합 GPU Dockerfile (CUDA, Python 3.12)
│   ├── main.py                        # 크롤러 진입점
│   ├── crawlers/                      # base(retry+스코어링) · nate_pann · bobaedream · dcinside · fmkorea · plugin_manager
│   ├── db/
│   │   ├── models.py                  # Post/Comment/Content/LLMLog/ScriptData + PostStatus
│   │   ├── session.py
│   │   └── migrations/                # (레거시) Python 마이그레이션 러너
│   ├── ai_worker/                     # 8-Phase AI 파이프라인 (패키지 경로 import)
│   │   ├── core/                      # main(진입점) · processor(루프) · gpu_manager · shutdown
│   │   ├── llm/transport.py           # call_llm / pick_model / resolve_model_id (CLI·API 백엔드)
│   │   ├── script/                    # client · chunker · normalizer · parser · logger
│   │   ├── scene/                     # director · validator · analyzer
│   │   ├── pipeline/content_processor.py  # Phase 1~8 통합 진입점
│   │   ├── tts/                       # fish_client · normalizer · number_reader
│   │   ├── video/                     # manager · comfy_client · prompt_engine · image_filter · video_utils · workflows/
│   │   └── renderer/                  # composer(진입점) · layout · _frames · _tts · _encode · thumbnail
│   ├── llm/                           # ★ llm-worker 게이트웨이 (Spring Boot, claude CLI 브릿지)
│   ├── uploaders/                     # base(UploaderRegistry) · youtube · uploader
│   ├── analytics/                     # collector(YouTube Analytics) · feedback(LLM 피드백 루프)
│   ├── dashboard_worker/              # jobs 테이블 폴링 실행 데몬
│   ├── monitoring/                    # alerting · daemon
│   └── test/
├── telegram/                          # 텔레그램 브리지 봇 (Node/TypeScript)
├── config/                            # 설정 허브
│   ├── settings.py                    # 전역 설정 (도메인 모듈 re-export)
│   ├── crawler.py / monitoring.py     # 도메인별 설정
│   ├── pipeline.json                  # 런타임 파이프라인 설정 (대시보드 편집)
│   ├── credentials.json               # API 키 / OAuth 토큰
│   ├── layout.json                    # 렌더러 레이아웃 (Single Source of Truth)
│   ├── scene_policy.json              # Mood별 씬 정책 (9개 프리셋)
│   └── video_styles.json              # Mood별 비주얼 스타일
├── assets/
│   ├── backgrounds/  fonts/  image/   # 배경 영상 · 폰트 · Mood Intro/Outro
│   ├── bgm/                           # Mood별 BGM (9개 카테고리)
│   ├── voices/                        # Fish Speech 참조 오디오 (WAV)
│   └── media/                         # 생성물 (tmp/videos 등, ComfyUI 공유 볼륨)
├── checkpoints/                       # 모델 파일 (Fish Speech / LTX-2 / Gemma 3 / 업스케일러)
├── scripts/                           # setup_docker_gpu · download_fish_speech · download_ltx2 · youtube_auth · tiktok_auth
└── docs/                              # 상세 문서 (architecture / pipeline / database / api / services / config)
```

---

## 로그 확인

```bash
# 항상 --tail 옵션 사용 (토큰/메모리 낭비 방지)
docker compose -f env/docker-compose.yml logs --tail 50 ai_worker
docker compose -f env/docker-compose.yml logs --tail 50 llm-worker
docker compose -f env/docker-compose.yml logs --tail 50 fish-speech
docker compose -f env/docker-compose.yml logs --tail 50 crawler

# GPU 사용 현황
nvidia-smi
```

---

## 상세 문서

| 문서 | 내용 |
|------|------|
| [`docs/architecture.md`](docs/architecture.md) | 시스템 전체 구조, 서비스 흐름도, 기술 스택, Post 상태 전이, VRAM 배분 |
| [`docs/pipeline.md`](docs/pipeline.md) | 8-Phase AI 파이프라인 상세, LLM 모델 라우팅, 4단계 폴백, 피드백 루프 |
| [`docs/database.md`](docs/database.md) | DB 스키마 ER, 테이블 컬럼, ScriptData JSON 구조, SQLAlchemy 패턴 |
| [`docs/api.md`](docs/api.md) | llm-worker REST API 명세, Fish Speech / ComfyUI API |
| [`docs/services.md`](docs/services.md) | Docker 서비스별 포트/볼륨/환경변수/의존성, 시작 순서 |
| [`docs/config.md`](docs/config.md) | settings.py 변수, pipeline.json / scene_policy.json / layout.json 키 설명 |
| [`docs/implementation-status.md`](docs/implementation-status.md) | 구현 완료 vs 미구현 현황 |
