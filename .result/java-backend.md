# java-backend

## 1. 작업 결과

Java Spring Boot 백엔드 전체 개편 — Post/Content 도메인 확장, Inbox/Editor/Progress 컨트롤러 기능 추가, TtsController·OverviewController·VoiceCatalogService 신규 생성, 기존 빌드 버그(GalleryController) 수정.

| 항목 | 파일 | 변경 유형 |
|------|------|---------|
| Post AI 분석 필드 4개 추가 | `domain/Post.java` | 수정 |
| Content ttsVoice/genInstructions 필드 추가 | `domain/Content.java` | 수정 |
| PostRepository 시간 기반 count 메서드 추가 | `domain/PostRepository.java` | 수정 |
| Inbox 필터/정렬 확장 + comments + analyze-batch | `controller/InboxController.java` | 수정 |
| Editor GET enrichment + voice + prompt-presets | `controller/EditorController.java` | 수정 |
| Progress pipeline_state 파싱 + progress enrich | `controller/ProgressController.java` | 수정 |
| voices.json/prompt_presets.json 카탈로그 서비스 | `settings/VoiceCatalogService.java` | 신규 |
| GET /api/tts/voices | `controller/TtsController.java` | 신규 |
| GET /api/overview | `controller/OverviewController.java` | 신규 |
| GalleryController IN_PROGRESS→RUNNING 버그 수정 | `controller/GalleryController.java` | 수정 |

## 2. 수정 내용

### Post.java
- `aiScore` (Integer), `aiReason` (length=500), `aiRecommended` (Boolean), `aiAnalyzedAt` (LocalDateTime) 필드 추가
- Lombok `@Getter @Setter`로 자동 생성

### Content.java
- `ttsVoice` (length=32), `genInstructions` (length=1000) 필드 추가

### PostRepository.java
- `countByCreatedAtAfter(LocalDateTime since)`: Spring Data 파생 메서드
- `countByStatusAndUpdatedAtAfter(PostStatus status, LocalDateTime since)`: JPQL 쿼리

### InboxController.java
- `GET /api/inbox`: `sort`(score|ai_score|newest), `since`(ISO datetime), `recommended`(Boolean) 파라미터 추가
  - ai_score 정렬: aiScore DESC + engagementScore DESC 복합
  - newest: createdAt DESC
  - since 필터: createdAt >= since
  - recommended 필터: aiRecommended == true
- `GET /api/inbox/{id}/comments`: CommentRepository.findByPostIdOrderByLikesDesc → limit 적용
- `POST /api/inbox/analyze-batch`: ids 지정 또는 COLLECTED & aiScore IS NULL 상위 건 AI_FITNESS 잡 생성 (최대 20)
- `AnalyzeBatchRequest` record 내부 정의

### EditorController.java
- `GET /api/editor/{id}`: ttsVoice, genInstructions, variantGroup, variantLabel 응답 추가
- `PUT /api/editor/{id}/voice`: VoiceCatalogService 키 검증 후 content.ttsVoice 저장
- `GET /api/editor/prompt-presets`: prompt_presets.json 목록 반환
- `SetVoiceRequest` record 내부 정의

### ProgressController.java
- ContentRepository, ObjectMapper 주입 추가
- PROCESSING 목록에 `progress` 맵 추가 (pipelineState JSON 파싱)
- `parseProgress(String)` 패키지-private 메서드: progress 키 추출 → 없으면 video_scenes_done 레거시 폴백

### VoiceCatalogService.java (신규)
- `loadVoices()`: config/voices.json 읽기, sampleUrl = /api/media/voices/{file} 합성
- `getDefaultVoice()`: pipeline.json의 tts_voice 값 (기본 "yura")
- `getPromptPresets()`: config/prompt_presets.json 읽기
- `isValidVoiceKey(String)`: null 허용, voices.json key 존재 여부 확인

### TtsController.java (신규)
- `GET /api/tts/voices`: { defaultVoice, voices: [...] }

### OverviewController.java (신규)
- `GET /api/overview?since=`: status별 counts, today(crawled/uploaded/declined), failedRecent(최근5), processing(+progress enrich)
- since 기본값: 오늘 자정

### GalleryController.java (버그 수정)
- `IN_PROGRESS` → `RUNNING` (JobStatus enum 값 불일치로 기존 빌드 실패 원인)

## 3. 테스트 결과

`./gradlew compileJava` — BUILD SUCCESSFUL

## 4. 수동 테스트 방법

```bash
# 서비스 시작
docker compose -f env/docker-compose.yml up -d backend

# 목소리 목록 (config/voices.json 필요)
curl http://localhost:8080/api/tts/voices

# 오버뷰
curl http://localhost:8080/api/overview

# inbox 필터 테스트
curl "http://localhost:8080/api/inbox?sort=newest&recommended=true"

# AI 배치 분석
curl -X POST http://localhost:8080/api/inbox/analyze-batch \
  -H 'Content-Type: application/json' -d '{"limit":5}'

# 보이스 설정
curl -X PUT http://localhost:8080/api/editor/1/voice \
  -H 'Content-Type: application/json' -d '{"voice":"yura"}'
```

## 5. 추천 commit message

```
feat: Java 백엔드 개편 — AI분석 필드, 보이스 카탈로그, Overview·TTS 컨트롤러 신규
```
