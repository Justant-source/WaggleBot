# external-ingest

## 1. 작업 결과

Again Spring(및 향후 다른 외부 서비스)이 사연을 WaggleBot 파이프라인(대본→TTS→렌더링)에
직접 밀어넣고 진행 상태를 폴링할 수 있도록 `/api/external/jobs` ingest+render API를 신규 구현.
X-Api-Key 인증, (site_code, origin_id) 멱등성, `variant_config` 기반 게시글별 `video_gen`/
`outro_text`/`auto_hd_render` 오버라이드, `PREVIEW_RENDERED` 도달 시 자동 HD_RENDER 큐잉까지 포함.
기존 크롤러/수신함/에디터 흐름은 전혀 건드리지 않음(신규 코드 경로만 추가, DB 스키마 변경 없음).

| 항목 | 파일 | 변경 유형 |
|------|------|---------|
| X-Api-Key 인증 필터 (`/api/external/**`만) | `backend/.../config/ExternalApiKeyFilter.java` | 신규 |
| POST/GET 컨트롤러 | `backend/.../controller/ExternalJobController.java` | 신규 |
| ingest 서비스 (멱등·재시도·variant_config) | `backend/.../external/ExternalIngestService.java` | 신규 |
| 요청 DTO | `backend/.../external/ExternalJobRequest.java` | 신규 |
| 댓글 삽입용 setter 추가 | `backend/.../domain/Comment.java` | 수정 |
| 댓글 중복 방지 조회 메서드 | `backend/.../domain/CommentRepository.java` | 수정 |
| 멱등 키 조회 메서드 | `backend/.../domain/PostRepository.java` | 수정 |
| `app.external.api-key` 프로퍼티 | `backend/src/main/resources/application.yml` | 수정 |
| `EXTERNAL_API_KEY` env 전달 | `env/docker-compose.yml`, `env/.env.example` | 수정 |
| outro_text 오버라이드 지원 | `worker/ai_worker/scene/director.py` | 수정 |
| `video_gen_enabled_for_post()` / `_resolve_post_outro_text()` | `worker/ai_worker/core/processor.py` | 수정 |
| 동일 오버라이드 반영(비활성 경로, 참고용) | `worker/ai_worker/pipeline/content_processor.py` | 수정 |

## 2. 수정 내용

### 계약 (POST /api/external/jobs)
```json
{
  "source": "again_spring", "externalId": "post_xxx", "title": "...", "body": "...",
  "comments": [{"author": "a", "body": "b", "likeCount": 1}],
  "paired": false, "options": {"videoGen": false, "autoHdRender": true}
}
```
- `source` → `posts.site_code`, `externalId` → `posts.origin_id` (기존 `uq_site_origin` 유니크 키 그대로 재사용 — 스키마 변경 없음)
- **멱등성**: 기존 Post가 있고 상태 ≠ `FAILED` → 재적재 없이 `{jobId, status}` 그대로 반환. `FAILED`면 title/body 갱신 + `APPROVED`로 되돌림(retryCount++, lastError=null) — 외부 재시도 지원
- 댓글은 크롤러(`worker/crawlers/base.py`)와 **동일한 해시 규칙**(`sha256(author:content)[:32]`)으로 `uq_post_comment` 중복 방지 — 재시도 시 중복 삽입 안 됨(직접 확인)
- `contents.variant_config`에 `{source, external_id, video_gen, paired, outro_text, auto_hd_render}` JSON 저장
  - `outro_text`: `paired=true`→"상대방의 사연이 궁금하면 댓글을 확인해주세요", 아니면 "여러분의 의견을 댓글로 남겨주세요"
  - `video_gen` 기본 `false`, `auto_hd_render` 기본 `true` (옵션 미지정 시)

### GET /api/external/jobs/{jobId}
- `jobId` = 생성된 `Post.id` (별도 Job 큐 아님)
- `status`, `progress`(pipeline_state.progress를 `ProgressController`와 동일한 snake→camel 변환), `externalId` 반환
- `PREVIEW_RENDERED`/`RENDERED`일 때만 `artifacts.{videoUrl,audioUrl}` (`/api/media/**` 상대경로) 포함
- `PREVIEW_RENDERED` + `variant_config.auto_hd_render=true`면 `GalleryController.hdRender()`와 동일하게 활성 `HD_RENDER` 잡을 조회하거나 없으면 새로 큐잉(멱등) — `hdRenderJobId` 반환

### 인증
- `ExternalApiKeyFilter extends OncePerRequestFilter` — `/api/external/`로 시작하는 경로만 검사, 그 외 전부 통과
- 키: `EXTERNAL_API_KEY` env → `app.external.api-key` 프로퍼티 (로컬 기본값 `change-me-external`)
- 불일치/누락 시 `401 {"error": "invalid or missing X-Api-Key", "status": 401}`

### Comment 엔티티
- `@Getter @NoArgsConstructor` → `@Getter @Setter @NoArgsConstructor`로 변경해 서비스에서 `new Comment()` + setter로 삽입 가능하게 함 (기존 필드/제약 변경 없음)

### Python — SceneDirector / processor
- `SceneDirector(..., outro_text: str | None = None)` 추가. 지정 시 `direct()`의 아웃트로 문구 `random.choice(fixed_texts)`를 건너뛰고 그 값을 그대로 사용
- `processor.py`: `_resolve_post_variant_config()` → `video_gen_enabled_for_post(post_id)`(variant_config.video_gen 우선, 없으면 전역 `VIDEO_GEN_ENABLED`), `_resolve_post_outro_text(post_id)` 추가. `_generate_video_clips()` 게이팅과 `render_stage()`/`process_with_retry()`의 `SceneDirector` 생성 양쪽에 배선(실제 운영 파이프라인 경로)
- `content_processor.py`(현재 main.py에서 미사용 — Phase1-8 통합 엔트리 문서화 목적 코드)도 동일 헬퍼로 일관되게 갱신

## 3. 테스트 결과물 위치

- Java: `cd backend && ./gradlew compileJava` → `BUILD SUCCESSFUL`
- Python: `python3 -m py_compile` 통과 + `env-ai_worker-1` 컨테이너 내부에서 실제 모듈 import·DB round-trip 스모크 테스트 수행(코드는 컨테이너 내부에 남기지 않고 즉시 정리 — DB에도 잔여 행 없음)
- 문서: `python3 scripts/lint_docs.py` → `PASS`
- 산출 파일 없음 (API 구현 작업 — 렌더링 산출물 생성 안 함)

## 4. 수동 테스트 방법

```bash
cd env
docker compose build backend && docker compose up -d --no-deps backend

# 인증 실패
curl -i -X POST localhost:8080/api/external/jobs \
  -H 'Content-Type: application/json' -H 'X-Api-Key: wrong' \
  -d '{"source":"again_spring","externalId":"post_1","title":"t","body":"b"}'
# → 401

# ingest
curl -s -X POST localhost:8080/api/external/jobs \
  -H 'Content-Type: application/json' -H 'X-Api-Key: change-me-external' \
  -d '{
    "source": "again_spring", "externalId": "post_1", "title": "제목", "body": "본문",
    "comments": [{"author":"a","body":"b","likeCount":1}],
    "paired": false, "options": {"videoGen": false, "autoHdRender": true}
  }'
# → {"ok":true,"jobId":<id>,"status":"APPROVED","externalId":"post_1"}

# 동일 요청 재전송 → 멱등 (같은 jobId/status 그대로 반환)

# 폴링
curl -s localhost:8080/api/external/jobs/<id> -H 'X-Api-Key: change-me-external'
```

실제로 위 흐름을 dev 환경(WaggleBot는 dev/prod 분리 없이 단일 스택 운영)에서 end-to-end 실행해
Post/Comment/Content(variant_config 정확히 일치) 생성과 `FAILED`→재ingest→`APPROVED` 되살림,
댓글 중복 미삽입까지 DB에서 직접 확인 후 테스트 데이터는 삭제함.

## 5. 추천 commit message

```
feat(api): Again Spring external ingest+render jobs
```
(이미 이 메시지로 `main`에 커밋 완료 — push는 하지 않음, 사용자 명시 요청 시 진행)

## 6. Doc-Sync — docs/_index.md 트리거 맵 기준 갱신 문서

| 트리거 | 문서 |
|--------|------|
| `backend/**/controller/**` | `docs/50-api/rest-spec.md` (External Jobs 섹션 신규) |
| `worker/ai_worker/pipeline/**`, `scene/**` | `docs/30-components/pipeline.md` (outro_text 오버라이드, video_gen 판정 노트) |
| `worker/ai_worker/core/processor.py` | `docs/60-runtime/pipeline-runtime.md` (게시글별 video_gen 오버라이드 절 신규) |
| `env/.env` 환경변수 추가(`EXTERNAL_API_KEY`) | `docs/20-containers/topology.md` (backend 환경변수·외부 API 링크) |

DB 스키마 변경 없음 → `docs/40-data/schema.md` 갱신 대상 아님.
