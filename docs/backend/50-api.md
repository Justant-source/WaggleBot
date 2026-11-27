# WaggleBot — API 명세 (L5)

> last-verified: 2026-11-27 · code-ref: `backend/src/main/java/com/wagglebot/controller/`, `backend/src/main/java/com/wagglebot/external/`, `backend/src/main/java/com/wagglebot/config/ExternalApiKeyFilter.java`, `worker/llm/src/main/java/com/wagglebot/llmworker/`, `worker/ai_worker/tts/synth.py`, `worker/ai_worker/tts/local_tts_client.py`, `worker/ai_worker/core/main.py`, `worker/ai_worker/core/progress.py`
> scope: llm-worker·backend·Local-TTS(외부)·ComfyUI API 엔드포인트 명세 — SSOT

## 서비스별 Base URL

| 서비스 | Base URL | 역할 |
|--------|----------|------|
| `llm-worker` | `http://llm-worker:8090` | Claude CLI 게이트웨이 (완전 구현) |
| `backend` | `http://backend:8080` | Spring Boot REST API (완전 구현) |
| `local-tts` | `http://local-tts:8500` | Local-TTS 외부 제공자(Supertonic). 네트워크 `local_tts_net`, 이 compose 서비스 아님 |
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
| `sonnet` | `claude-sonnet-5-5` |
| `opus` | `claude-opus-5-5` |

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

> 내부 처리 흐름(sequenceDiagram + JSON Mode flowchart) → [`flows.md`](../worker/50-api.md)

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
| `GET` | `/api/progress` | 전체 상태별 카운트 + PROCESSING 목록 + FAILED 목록(최근 20건, lastError 포함). `processing[]`는 `id,title,siteCode,updatedAt`와 `progress{currentPhase,phaseName,phaseStartedAt,lastHeartbeatAt,updatedAt,done,...}`(없으면 null). `progress`는 `content_runtime_state(progress)`가 정본이고 `pipeline_state`는 롤링 업그레이드 폴백. 소비자는 `lastHeartbeatAt`이 수 분 이상 갱신되지 않으면 '멈춤'으로 판정한다(워커는 30초마다 갱신, 30분 무활동이면 자동 회수) |
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
| `GET` | `/api/tts/voices` | 보이스 프리셋 목록(`M1~M5`·`F1~F5`, `config/voices.json` v4) + `defaultVoice`(`pipeline.json tts_voice` 그대로: `default`=자동·글별 랜덤, 프리셋 대문자, 구 키 보존) |
| `GET` | `/api/tts/voices/{key}/sample` | 사전 생성 샘플 `assets/voices/voice_preview_{KEY}.mp3` 스트리밍(없으면 404) |

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
  "options": {
    "videoGen": false, "autoHdRender": true,
    "priority": "MARKETING_CRITICAL", "deadlineAt": "2026-08-14T12:00:00+09:00",
    "preScripted": true, "renderProfile": "marketing_fast"
  }
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
  - `priority`: `source=again_spring`은 요청값과 무관하게 `MARKETING_CRITICAL`로 저장되어 일반 잡보다 먼저 선택된다.
  - `deadline_at`: 외부 SLA 시각. critical 요청에서 생략하면 ingest 시각부터 10분으로 설정한다. 지난 잡은 실패하지 않고 `degraded=true`로 계속 진행하며 댓글 낭독을 1건으로 줄인다.
  - `pre_scripted=true`: Again Spring에서 원격 Claude 청킹 대신 본문을 결정적으로 분할해 즉시 TTS 단계로 보낸다.

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
  "priority": "MARKETING_CRITICAL",
  "deadlineAt": "2026-08-14T12:00:00+09:00",
  "degraded": false,
  "progress": { "currentPhase": 7, "phaseName": "비디오 클립", "lastHeartbeatAt": "2026-08-14T03:00:00+00:00", "scenesDone": 3, "totalScenes": 5 },
  "generationDiagnostics": { "story_duration_ms": 29800, "comment_duration_ms": 8200, "outro_duration_ms": 2400, "final_duration_ms": 40400, "comment_count": 2 },
  "artifacts": { "videoUrl": "/api/media/tmp/videos/....mp4", "audioUrl": "/api/media/audio/....wav", "thumbnailUrl": "/api/media/thumbnails/again_spring/post_xxx_intro.png" },
  "hdRenderJobId": 456
}
```
- `progress`: `content_runtime_state(progress)`를 `ProgressController`와 동일한 규칙으로 snake_case→camelCase 변환한다. 롤링 업그레이드 중에는 `contents.pipeline_state.progress`를 읽기 폴백으로만 사용한다.
- `generationDiagnostics`: 프롬프트·LLM 원문을 제외한 품질 사실이다. 본문/댓글/아웃트로/최종 길이와 댓글 수를 제공한다.
- `status=FAILED`이면 항상 `failureCode`, `failureStage`, `retryable`, `errorSummary`를 추가한다. 예: DB 스냅샷 충돌은 `INFRA_DB_CONFLICT`; 품질/대본 오류는 해당 품질 코드다.
- `priority`, `deadlineAt`, `degraded`, `degradeReasons`: 마케팅 큐/SLA 상태. `degraded`는 품질 축소 상태일 뿐 terminal 실패가 아니다.
- `artifacts`: `status`가 `PREVIEW_RENDERED`/`RENDERED`일 때만 포함
- `artifacts.thumbnailUrl`/`thumbUrl`: 인트로(메타포+제목) PNG. `upload_meta.thumbnail_path`가 있고 파일이 존재할 때만 포함. ASM이 YouTube `thumbnails.set`에 올린다 (Shorts oar 자동프레임 대체).
, `MediaController`(`/api/media/**`) 기준 상대 경로.
- `hdRenderJobId`: `status=PREVIEW_RENDERED` + `variant_config.auto_hd_render=true`일 때만 등장. `GalleryController.hdRender()`와 동일하게 활성 `HD_RENDER` 잡이 있으면 그 ID를, 없으면 새로 큐잉한 잡 ID를 반환(중복 큐잉 방지).

---

## Local-TTS API (:8500, 외부 제공자)

Python `worker/ai_worker/tts/synth.py`가 `local_tts_client.py`(Local-TTS 클라이언트 **복사본**)로 호출한다. 서버는 별도 저장소(`/home/justant/Data/Local-TTS`)가 운영하며 이 compose에는 없다. 컨테이너 간 주소 `http://local-tts:8500`(외부 네트워크 `local_tts_net`), 호스트 `127.0.0.1:8500`. 전체 계약은 Local-TTS `docs/api.md`·`docs/CONTRACT.md`가 정본이고, 아래는 WaggleBot이 쓰는 부분만 요약한다. 클라이언트 동작(재시도·오류 매핑·재큐·보이스 해석)은 [worker/30-components/local-tts-client.md](../worker/30-components/local-tts-client.md)가 정본이다.

**공통 헤더:** `X-Client-Id: wagglebot`(= 프로필 네임스페이스), 토큰이 설정된 서버면 `Authorization: Bearer <TTS_SERVER_TOKEN>`, 생성 시 `Idempotency-Key`(= `options.request_id`).

| 호출 | 용도 |
|------|------|
| `POST /v1/jobs` | 합성 job 생성(202) |
| `GET /v1/jobs/{id}?wait=25&since_rev=N` | 상태 대기(long-poll) |
| `GET /v1/jobs/{id}/audio` | 최종 wav |
| `DELETE /v1/jobs/{id}` | 결과 파일 삭제 |
| `POST /v1/jobs/{id}:cancel` | 대기 시간 초과 시 취소 |
| `GET /readyz` | 서버 준비 확인(`wait_for_tts_server`) |
| `POST /v1/profiles/wagglebot/shorts-ko/versions` 등 | 발음 프로필 업로드·검증·미리보기·활성화 — `worker/tools/sync_tts_profile.py`만 사용 |

**Request (job 생성, `synth.build_options` 기준):**
```json
{
  "input": "<prenormalize 결과>",
  "options": {
    "voice": "F2",
    "lang": "ko",
    "speed": 1.1,
    "normalize": {"enabled": true, "profile": "wagglebot/shorts-ko"},
    "chunk": {"mode": "max_chars", "max_chars": 120},
    "postprocess": {"loudnorm": {"enabled": true, "i": -16, "tp": -1.5}},
    "output": {"format": "wav"},
    "request_id": "wb-<post_id>-<scene_type>-<uuid8>"
  }
}
```

**오류 분류:** 연결 실패·타임아웃·429·503·502/504는 클라이언트가 `TTS_SERVER_RETRIES`회 재시도한 뒤, 대기 초과(`WaitTimeout`)와 재시도 가능 job 실패(`error.retryable`)는 즉시 `TTSUnavailable`(일시 장애 → APPROVED 재큐). **500 등 그 밖의 5xx는 일시 장애가 아니다** — 총 2회 시도(2회차는 새 키 `<request_id>-r1`: 서버가 실패 job을 같은 키로 replay하므로)한 뒤 `TTSError`(FAILED). `empty_input`은 `ValueError`, 그 밖의 400/413/422·401/403/404/409/410·영구 job 실패는 `TTSError`(일반 실패). 전체 표는 local-tts-client.md §6.

**설정값 (config/settings.py):** `TTS_SERVER_URL`, `TTS_SERVER_TOKEN`, `TTS_SERVER_TIMEOUT_SEC=120`, `TTS_SERVER_RETRIES=3`, `TTS_SERVER_MAX_WAIT_SEC=3600`(job 완료 대기만), `TTS_PROFILE=wagglebot/shorts-ko`, `TTS_CLIENT_ID=wagglebot`, `TTS_SPEED=1.1` → [worker/20-containers](../worker/20-containers.md#tts-설정)

> 폐기: Fish Speech API(`POST /v1/tts`, `reference_id`·`use_memory_cache`, 감정 마커), `fish-speech:8080`/`:8082`. ADR-0005는 폐기됨 → [ADR-0006](../shared/90-adr/0006-local-tts-provider.md).

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

### 실패 코드·단계 분류 (2026-08-15, `worker/ai_worker/core/main.py::_classify_failure`)

`failureStage`는 `phaseName`을 영문 상수로 매핑해 `WAGGLE:` 접두사를 붙인다(`progress.py::normalize_failure_stage`):

| phaseName | failureStage |
|---|---|
| 자원 분석 | `WAGGLE:RESOURCE_ANALYSIS` |
| 대본 생성 | `WAGGLE:SCRIPT_GENERATION` |
| 씬 구성 | `WAGGLE:SCENE_COMPOSE` |
| 비디오 프롬프트 | `WAGGLE:VIDEO_PROMPT` |
| 비디오 클립 | `WAGGLE:VIDEO_CLIP` |
| FFmpeg 렌더링 | `WAGGLE:FFMPEG_RENDER` |
| TTS 합성 | `WAGGLE:TTS_SYNTHESIS` |

매핑 안 되는 phaseName은 `WAGGLE:PHASE_UNKNOWN`으로 폴백한다(빈 값 대신).

`failureCode` 분류(10종)와 `retryable` 여부:

| failureCode | retryable | 의미 |
|---|---|---|
| `INFRA_DB_CONFLICT` | true | DB 동시성 충돌 |
| `INFRA_TIMEOUT` | true | 페이즈 타임아웃 |
| `INFRA_OOM` | true | 메모리 부족 |
| `INFRA_GPU_UNAVAILABLE` | true | GPU 사용 불가 |
| `RENDER_FFMPEG_ERROR` | true | FFmpeg 인코딩 실패 |
| `RENDER_ASSET_MISSING` | **false** | 입력 자산 누락 (같은 입력=같은 결과) |
| `RENDER_INVALID_INPUT` | **false** | 입력 데이터 자체가 잘못됨 |
| `RENDER_UNKNOWN` | true | 미분류 렌더 오류 |
| `TTS_GENERATION_FAILED` | true | TTS 합성 실패 |
| `VARIANT_LLM_ERROR` | **false** | LLM 콘텐츠 거부 |

`error`(예외 메시지 원문, 최대 500자)는 절대 비워두지 않는다. ASM `waggle_recovery.py`는
`failureCode`/`failure_code`, `failureStage`/`failure_stage`, `error`/`error_summary`/`errorSummary`
키를 모두 방어적으로 읽으므로 camelCase/snake_case 어느 쪽을 보내도 호환된다.
