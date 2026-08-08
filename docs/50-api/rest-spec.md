# WaggleBot — API 명세 (L5)

> last-verified: 2026-08-08 · code-ref: `backend/src/main/java/com/wagglebot/controller/`, `backend/src/main/java/com/wagglebot/external/`, `backend/src/main/java/com/wagglebot/config/ExternalApiKeyFilter.java`, `worker/llm/src/main/java/com/wagglebot/llmworker/`, `worker/ai_worker/tts/fish_client.py` · 2026-08-08 ClaudeService 재시도 로직 추가
> scope: llm-worker·backend·Fish Speech·ComfyUI API 엔드포인트 명세 — SSOT

## 서비스별 Base URL

| 서비스 | Base URL | 역할 |
|--------|----------|------|
| `llm-worker` | `http://llm-worker:8090` | Claude CLI 게이트웨이 (완전 구현) |
| `backend` | `http://backend:8080` | Spring Boot REST API (완전 구현) |
| `fish-speech` | `http://fish-speech:8080` | OpenAudio S1-mini TTS 서비스 |
| `comfyui` | `http://comfyui:8188` | 비디오 생성 (외부 이미지) |

---

## llm-worker API (:8090)

### POST /v1/invoke

LLM 호출. Python `call_llm()` 함수가 이 엔드포인트를 사용.

**Request Body:**
```json
{
  "prompt": "처리할 텍스트 또는 질문",
  "systemPrompt": "시스템 프롬프트 (선택)",
  "model": "haiku",
  "jsonMode": false,
  "maxTokens": 2048,
  "temperature": 0.7,
  "callType": "chunk",
  "correlationId": "post-123-chunk",
  "timeoutMs": 0
}
```

| 필드 | 타입 | 기본값 | 설명 |
|------|------|--------|------|
| `prompt` | string | **필수** | 사용자 프롬프트 |
| `systemPrompt` | string | null | 시스템 프롬프트 |
| `model` | string | `claude-haiku-4-5-20251001` | 모델 별칭 또는 전체 ID |
| `jsonMode` | boolean | false | true 시 JSON 응답 강제 + 파싱 |
| `maxTokens` | int | 2048 | 최대 출력 토큰 (advisory) |
| `temperature` | float | 0.7 | 온도 (advisory — claude CLI 미지원) |
| `callType` | string | `raw` | 로깅용 레이블 |
| `correlationId` | string | null | 추적 ID |
| `timeoutMs` | long | 0 | 0=기본값(120초) |

**모델 별칭 매핑:**
| 별칭 | 실제 모델 ID |
|------|------------|
| `haiku` | `claude-haiku-4-5-20251001` |
| `sonnet` | `claude-sonnet-4-6` |
| `opus` | `claude-opus-4-8` |

**Response (200):**
```json
{
  "text": "LLM 응답 텍스트",
  "model": "claude-haiku-4-5-20251001",
  "jsonValid": false,
  "stopReason": "end_turn",
  "durationMs": 1234,
  "callType": "chunk",
  "correlationId": "post-123-chunk"
}
```

**에러 응답 및 재시도 정책:**
| HTTP | 예외 | 원인 | 재시도 |
|------|------|------|--------|
| 400 | IllegalArgumentException | prompt 누락 | ✗ |
| 429 | QueueFullException | 큐 포화 (queueCapacity=500) | ✗ |
| 502 | CliFailedException | Claude CLI 비정상 종료 (3회 재시도 후) | ✓ 내부 3회 지수백오프 (1s, 2s, 4s) |
| 502 | CliFailedException | 인증/권한 오류 감지 시 즉시 실패 | ✗ (재시도 불가) |
| 504 | InvocationTimeoutException | 타임아웃 초과 | ✗ |

**재시도 정책 상세:**
- **ClaudeService.runClaudeWithRetry()** 내부에서 최대 3회 시도
- 지수 백오프: 1초 → 2초 → 4초
- 인증 오류 감지 시: 즉시 502 반환 (재시도 안 함)
  - 감지 패턴: "auth", "login", "oauth", "credential", "unauthorized", "permission denied", "invalid token"
- 호출자는 502 수신 시 최대 3회 재시도가 이미 내부에서 처리됨을 인지

### GET /healthz

서비스 헬스 체크.

**Response (200):** `{"status": "ok"}`

### GET /actuator/health

Spring Actuator 헬스. `ClaudeCliHealthIndicator` 포함 (`claude --version` 30초 캐싱).

> 내부 처리 흐름(sequenceDiagram + JSON Mode flowchart) → [`flows.md`](flows.md)

---

## backend API (:8080)

Spring Boot 3.3 REST API. 전체 Controller 구현 완료.

### Inbox (`/api/inbox`)

| Method | Path | 설명 |
|--------|------|------|
| `GET` | `/api/inbox` | COLLECTED 게시글 목록 (engagementScore 내림차순, 페이지네이션) + tier1/2/3 카운트 |
| `POST` | `/api/inbox/{id}/approve` | COLLECTED → EDITING + GENERATE_SCRIPT Job 생성 |
| `POST` | `/api/inbox/{id}/decline` | → DECLINED |
| `POST` | `/api/inbox/batch` | 배치 승인/거절. 응답: `{processed, failed:[{id,error}], action}` |
| `POST` | `/api/inbox/analyze-batch` | 선택 게시글에 AI_FITNESS Job 일괄 생성 |
| `POST` | `/api/inbox/{id}/analyze` | AI_FITNESS Job 생성 (게시글 적합성 분석) |
| `GET` | `/api/inbox/{id}/comments` | 게시글 댓글 목록 |
| `GET` | `/api/inbox/sites` | `CrawlerRegistry` 기반 등록 사이트 목록 |
| `POST` | `/api/inbox/crawl` | MANUAL_CRAWL Job 생성 |
| `GET` | `/api/inbox/jobs/{jobId}` | Job 상태 폴링 |

### Editor (`/api/editor`)

| Method | Path | 설명 |
|--------|------|------|
| `GET` | `/api/editor` | EDITING 게시글 목록 |
| `GET` | `/api/editor/{id}` | 게시글 + ScriptData + 설정 제약값 |
| `PUT` | `/api/editor/{id}/script` | 대본 수동 저장 (ScriptDataDto) |
| `POST` | `/api/editor/{id}/generate` | GENERATE_SCRIPT Job 생성 (model/extra_instructions 선택) |
| `POST` | `/api/editor/{id}/tts-preview` | TTS_PREVIEW Job 생성 |
| `PUT` | `/api/editor/{id}/voice` | 음성 키 변경 |
| `GET` | `/api/editor/prompt-presets` | 대본 생성 프롬프트 프리셋 목록 |
| `POST` | `/api/editor/{id}/confirm` | EDITING → APPROVED (최종 확인) |
| `GET` | `/api/editor/jobs/{jobId}` | Job 상태 폴링 |

### Gallery (`/api/gallery`)

| Method | Path | 설명 |
|--------|------|------|
| `GET` | `/api/gallery` | PREVIEW_RENDERED/RENDERED/UPLOADED 게시글 목록 (updatedAt 내림차순) + Content |
| `POST` | `/api/gallery/{id}/hd-render` | HD_RENDER Job 생성 |
| `POST` | `/api/gallery/{id}/upload` | UPLOAD Job 생성 (platform 선택) |

### Progress (`/api/progress`)

| Method | Path | 설명 |
|--------|------|------|
| `GET` | `/api/progress` | 전체 상태별 카운트 + PROCESSING 목록 + FAILED 목록(최근 20건, lastError 포함) |
| `POST` | `/api/progress/{id}/retry` | FAILED → APPROVED, retryCount++, lastError=null |

### Analytics (`/api/analytics`)

| Method | Path | 설명 |
|--------|------|------|
| `GET` | `/api/analytics/funnel` | 상태별 게시글 카운트 |
| `POST` | `/api/analytics/youtube/fetch` | FETCH_YT_ANALYTICS Job 생성 |
| `POST` | `/api/analytics/insights` | AI_INSIGHT Job 생성 (LLM 인사이트) |
| `POST` | `/api/analytics/feedback/apply` | FEEDBACK_APPLY Job 생성 |
| `GET` | `/api/analytics/performance` | 성과 데이터 조회 |
| `POST` | `/api/analytics/ab/create` | AB_CREATE Job 생성 |
| `POST` | `/api/analytics/ab/evaluate` | AB_EVALUATE Job 생성 |
| `POST` | `/api/analytics/ab/apply-winner` | AB_APPLY_WINNER Job 생성 |
| `GET` | `/api/analytics/jobs/{jobId}` | Job 상태 폴링 |

### LLM Logs (`/api/llm-logs`)

| Method | Path | 설명 |
|--------|------|------|
| `GET` | `/api/llm-logs` | LLM 호출 이력 (callType/postId/success 필터, createdAt 내림차순, 페이지네이션) |
| `GET` | `/api/llm-logs/call-types` | 기록된 callType 목록 |
| `GET` | `/api/llm-logs/{id}` | 단건 조회 |

### Settings (`/api/settings`)

| Method | Path | 설명 |
|--------|------|------|
| `GET` | `/api/settings` | pipeline.json 전체 조회 |
| `PUT` | `/api/settings` | pipeline.json 저장 |
| `GET` | `/api/settings/credentials` | 인증 정보 조회 (시크릿 마스킹) |
| `PUT` | `/api/settings/credentials` | 인증 정보 저장 |
| `GET` | `/api/settings/health` | 서비스 헬스 상태 |

### Media (`/api/media`)

정적 파일 서빙 — `/app/media/` 경로의 오디오/비디오/썸네일 파일을 HTTP로 노출.

### Overview (`/api/overview`)

| Method | Path | 설명 |
|--------|------|------|
| `GET` | `/api/overview` | 대시보드 요약 지표 |

### TTS (`/api/tts`)

| Method | Path | 설명 |
|--------|------|------|
| `GET` | `/api/tts/voices` | 등록된 음성 키 목록 |

### External Jobs (`/api/external/jobs`) — 외부 연동 ingest+render

Again Spring 등 **외부 서비스**가 사연을 WaggleBot 파이프라인(대본→TTS→렌더링)에 밀어넣고
진행 상태를 폴링하기 위한 엔드포인트. `com.wagglebot.config.ExternalApiKeyFilter`가
`/api/external/**` 전체에 `X-Api-Key` 인증을 강제한다 (그 외 경로는 영향 없음).

**인증:** 헤더 `X-Api-Key: <값>` — 값은 환경변수 `EXTERNAL_API_KEY`(로컬 기본값 `change-me-external`,
Spring 프로퍼티 `app.external.api-key`). 누락·불일치 시 `401 {"error": "...", "status": 401}`.

| Method | Path | 설명 |
|--------|------|------|
| `POST` | `/api/external/jobs` | 사연 ingest — Post/Comment/Content 생성 후 파이프라인 큐(APPROVED)로 진입 |
| `GET` | `/api/external/jobs/{jobId}` | 진행 상태 폴링. `jobId` = 생성된 Post.id |

**POST 요청 바디:**
```json
{
  "source": "again_spring",
  "externalId": "post_xxx",
  "title": "...",
  "body": "...",
  "comments": [{"author": "a", "body": "b", "likeCount": 1}],
  "paired": false,
  "options": {"videoGen": false, "autoHdRender": true}
}
```

- `source` → `posts.site_code`, `externalId` → `posts.origin_id`. 유니크 키 `uq_site_origin(site_code, origin_id)` 그대로 사용.
- **멱등성**: 동일 `(source, externalId)` Post가 이미 있고 상태가 `FAILED`가 아니면 재적재 없이 기존 `{jobId, status}`를 그대로 반환. `FAILED`면 title/body를 갱신하고 `APPROVED`로 되돌려 재처리시킨다(retryCount++, lastError=null).
- 댓글은 크롤러(`worker/crawlers/base.py`)와 동일한 `sha256(author:content)[:32]` 해시로 `uq_post_comment` 중복을 방지한다.
- `contents.variant_config`에 다음 JSON을 저장 — `ai_worker.core.processor.video_gen_enabled_for_post()`와 `SceneDirector.outro_text`가 읽는다:
  ```json
  {
    "source": "again_spring",
    "external_id": "post_xxx",
    "video_gen": false,
    "paired": false,
    "outro_text": "여러분은 어떻게 생각하세요? 댓글로 알려주세요.",
    "auto_hd_render": true
  }
  ```
  - `video_gen`: `options.videoGen`(기본 `false`) — 게시글 단위로 전역 `VIDEO_GEN_ENABLED`를 오버라이드
  - `outro_text`: `paired=true`면 `"상대방의 사연도 궁금하시죠? 댓글에서 확인해 보세요."`, 아니면 `"여러분은 어떻게 생각하세요? 댓글로 알려주세요."` — `SceneDirector`가 mood 기본 문구의 `random.choice()`를 건너뛰고 이 값을 그대로 사용
  - `auto_hd_render`: `options.autoHdRender`(기본 `true`) — GET 폴링에서 `PREVIEW_RENDERED` 도달 시 자동 `HD_RENDER` 잡 큐잉 여부

**POST 응답 (200):**
```json
{ "ok": true, "jobId": 123, "status": "APPROVED", "externalId": "post_xxx" }
```

**GET 응답 (200):**
```json
{
  "ok": true,
  "jobId": 123,
  "status": "PREVIEW_RENDERED",
  "externalId": "post_xxx",
  "progress": { "currentPhase": 7, "phaseName": "비디오 클립", "scenesDone": 3, "totalScenes": 5 },
  "artifacts": { "videoUrl": "/api/media/tmp/videos/....mp4", "audioUrl": "/api/media/audio/....wav" },
  "hdRenderJobId": 456
}
```
- `progress`: `contents.pipeline_state.progress`를 `ProgressController`와 동일한 규칙으로 snake_case→camelCase 변환. 없으면 `null`.
- `artifacts`: `status`가 `PREVIEW_RENDERED`/`RENDERED`일 때만 포함, `MediaController`(`/api/media/**`) 기준 상대 경로.
- `hdRenderJobId`: `status=PREVIEW_RENDERED` + `variant_config.auto_hd_render=true`일 때만 등장. `GalleryController.hdRender()`와 동일하게 활성 `HD_RENDER` 잡이 있으면 그 ID를, 없으면 새로 큐잉한 잡 ID를 반환(중복 큐잉 방지).

---

## Fish Speech API (:8082 외부, :8080 컨테이너 내부)

Python `worker/ai_worker/tts/fish_client.py`가 직접 호출한다. 컨테이너는 OpenAudio S1-mini를 로드한 Fish Speech API 서버이며, 참조 음성은 우선 `reference_id` 폴더 구조를 사용한다.

**주요 엔드포인트:**
```http
POST /v1/tts
```

**Request Body (reference_id 경로):**
```json
{
  "text": "(joyful) 안녕하세요.",
  "format": "wav",
  "chunk_length": 200,
  "normalize": false,
  "temperature": 0.8,
  "top_p": 0.8,
  "repetition_penalty": 1.1,
  "reference_id": "yura",
  "use_memory_cache": "on"
}
```

**레거시 base64 폴백:** `reference_id` 폴더가 없고 평면 파일만 있으면 `references: [{audio, text}]`를 보낸다. 둘 다 없으면 `references: []`로 기본 음색 합성을 시도하고 경고 로그를 남긴다.

**Response:** `audio/wav` binary.

**설정값 (config/settings.py):**
- `FISH_SPEECH_TIMEOUT = 300s`
- `FISH_SPEECH_TEMPERATURE = 0.8`
- `FISH_SPEECH_TOP_P = 0.8`
- `FISH_SPEECH_REPETITION_PENALTY = 1.1`
- `FISH_SPEECH_USE_MEMORY_CACHE = "on"`
- `FISH_SPEECH_NORMALIZE = false`

---

## ComfyUI API (:8188)

Python `comfy_client.py`가 워크플로우 JSON 제출.

```
POST /prompt            - 워크플로우 JSON 제출, prompt_id 반환
GET  /queue             - 큐 상태 조회
GET  /history/{prompt_id} - 완료된 작업 결과
GET  /system_stats      - GPU/VRAM 상태 (헬스체크)
```

**워크플로우 파일 위치:** `worker/ai_worker/video/workflows/` (ComfyUI와 볼륨 공유)
