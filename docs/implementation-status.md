# WaggleBot — 구현 현황

> **last-verified:** 2026-06-11 (commit `3ba0d15`)
> **scope:** 구현 완료·미완료 현황, 버그 픽스 이력

현재 코드베이스의 구현 완료/미완료 상태 정리. (2026-06-11 기준)

## 전체 현황 요약

전체 파이프라인(크롤링→AI 처리→렌더링→업로드) 구현 완료. 대시보드 UI·REST API·Python 워커 전체 운영 가능.

| 서비스 | 상태 | 비고 |
|--------|------|------|
| `llm-worker` | ✅ 완전 구현 | Claude CLI 게이트웨이 |
| `backend` | ✅ 완전 구현 | 전체 Controller + Domain + Service |
| `frontend` | ✅ 완전 구현 | 7개 어드민 페이지 + 공용 컴포넌트 |
| `worker/crawlers` | ✅ 완전 구현 | 4개 사이트 플러그인 + 플러그인 매니저 |
| `worker/ai_worker` | ✅ 완전 구현 | 8-Phase 파이프라인 전체 |
| `worker/db` | ✅ 완전 구현 | SQLAlchemy 모델 + 마이그레이션 |
| `worker/uploaders` | ✅ 완전 구현 | YouTube 업로더 |
| `worker/analytics` | ✅ 완전 구현 | 성과 수집 + LLM 피드백 루프 + A/B 테스트 파이프라인 통합 |
| `worker/monitoring` | ✅ 완전 구현 | 헬스체크 + 알림 데몬 |
| `worker/dashboard_worker` | ✅ 완전 구현 | Job 폴링 실행 데몬 |
| `config/` | ✅ 완전 구현 | settings.py + JSON 설정 파일 전체 |
| `env/` | ✅ 완전 구현 | docker-compose.yml + Dockerfile 전체 + ltxvideo_patches.py |
| `telegram-bridge` | ✅ 완전 구현 | 파이프라인 제어(/status,/posts,/approve,/reject,/crawl) + 파일관리/Git/알림 |

---

## ✅ 구현 완료

### backend (`backend/`)

```
src/main/java/com/wagglebot/
├── WagglebotApplication.java
├── common/
│   ├── JobStatus.java / JobType.java / PostStatus.java
│   ├── ScriptDataDto.java / ScriptDataMapper.java
│   └── converter/JsonNodeConverter.java         ✅ JPA JSON 컨버터
├── config/CorsConfig.java                       ✅ CORS 설정
├── controller/
│   ├── InboxController.java                     ✅ 수신함 CRUD + 배치 + Job 폴링
│   ├── EditorController.java                    ✅ 편집실 + TTS 프리뷰 + 대본 저장
│   ├── GalleryController.java                   ✅ 갤러리 목록 + HD 렌더 + 업로드
│   ├── ProgressController.java                  ✅ 처리 현황 + FAILED 목록 + 재시도
│   ├── AnalyticsController.java                 ✅ 퍼널 + YouTube 지표 + LLM 인사이트
│   ├── LlmLogController.java                    ✅ LLM 이력 조회
│   ├── SettingsController.java                  ✅ pipeline.json + credentials 관리
│   └── MediaController.java                     ✅ 미디어 파일 서빙
├── domain/
│   ├── Post.java + PostRepository.java          ✅ (last_error 컬럼 포함)
│   ├── Content.java + ContentRepository.java    ✅
│   ├── Comment.java + CommentRepository.java    ✅
│   ├── Job.java + JobRepository.java            ✅
│   └── LlmLog.java + LlmLogRepository.java      ✅
├── exception/GlobalExceptionHandler.java        ✅
├── job/JobService.java                          ✅ Job 큐 CRUD
└── settings/SettingsService.java                ✅ pipeline.json / credentials.json R/W
resources/db/migration/
├── V1__jobs_table.sql                           ✅ Flyway 자동 적용
└── V2__base_schema.sql                          ✅
```

### frontend (`frontend/`)

```
app/(admin)/admin/
├── inbox/page.tsx          ✅ 게시글 목록 + 티어 필터 + 배치 승인/거절 + toast 피드백
├── editor/page.tsx         ✅ EDITING 목록
├── editor/[postId]/page.tsx ✅ 대본 편집 + TTS 미리듣기 + Job 폴링
├── gallery/page.tsx        ✅ 썸네일 목록 + 9:16 풀스크린 모달 + HD렌더/업로드
├── progress/page.tsx       ✅ 상태 카운트 + PROCESSING(멈춤 배지) + FAILED(오류 표시 + 재시도)
├── analytics/page.tsx      ✅ 퍼널 차트 + YouTube 지표
├── llm-logs/page.tsx       ✅ LLM 호출 이력 테이블
└── settings/page.tsx       ✅ pipeline.json 폼 편집
components/
├── admin/shell/            ✅ Sidebar + Header
├── admin/AdminStatCard     ✅
├── admin/AdminSection      ✅
└── ui/                     ✅ button/badge/toast/dialog 등 shadcn 기반
lib/
├── api/                    ✅ inbox/editor/gallery/progress/analytics/llm-logs/settings API 클라이언트
├── hooks/                  ✅
└── types/index.ts          ✅ Post/Content/Job/LlmLog TypeScript 타입 (lastError 포함)
```

### worker (`worker/`)

```
worker/
├── main.py                              ✅ 크롤러 진입점
├── crawlers/
│   ├── base.py                          ✅ retry + engagement score 스코어링 + 6시간 반감기
│   ├── nate_pann.py                     ✅
│   ├── bobaedream.py                    ✅
│   ├── dcinside.py                      ✅
│   ├── fmkorea.py                       ✅
│   └── plugin_manager.py               ✅ CrawlerRegistry 동적 조회
├── db/
│   ├── models.py                        ✅ Post/Comment/Content/LLMLog/ScriptData + last_error
│   ├── session.py                       ✅ SessionLocal
│   └── migrations/                      ✅ 007개 SQL + runner.py
├── ai_worker/
│   ├── core/
│   │   ├── main.py                      ✅ 진입점 + _mark_post_failed(last_error 저장)
│   │   ├── processor.py                 ✅ APPROVED 폴링 루프
│   │   ├── gpu_manager.py               ✅ VRAM 세마포어 + nvidia-smi 연동
│   │   └── shutdown.py                  ✅ 그레이스풀 종료
│   ├── llm/transport.py                 ✅ call_llm/call_llm_raw/pick_model (CLI·API 백엔드 분기)
│   ├── script/
│   │   ├── client.py                    ✅ generate_script + _SCRIPT_SYSTEM 프롬프트
│   │   ├── chunker.py                   ✅ chunk_with_llm
│   │   ├── logger.py                    ✅
│   │   └── (parser, normalizer)         ✅
│   ├── scene/
│   │   ├── director.py                  ✅ SceneDirector + assign_video_modes
│   │   ├── validator.py                 ✅ validate_and_fix
│   │   └── analyzer.py                  ✅ analyze_resources → ResourceProfile
│   ├── pipeline/content_processor.py   ✅ Phase 1~8 통합 (Phase 5∥6 asyncio.gather)
│   ├── tts/
│   │   ├── fish_client.py               ✅ synthesize + 워밍업 센티널 스킵
│   │   ├── normalizer.py                ✅ 한국어 전처리
│   │   └── number_reader.py             ✅ 숫자 읽기
│   ├── video/
│   │   ├── manager.py                   ✅ 비디오 클립 오케스트레이션 + 4단계 폴백
│   │   ├── comfy_client.py              ✅ ComfyUI API + 적응형 폴링 + 워크플로우 캐시
│   │   ├── prompt_engine.py             ✅ 한→영 프롬프트 변환
│   │   ├── image_filter.py              ✅ I2V 적합성 점수
│   │   ├── video_utils.py               ✅ FFmpeg 후처리 + 프레임/해상도 검증
│   │   └── workflows/                   ✅ ComfyUI 워크플로우 JSON
│   │       ├── t2v_ltx2_distilled.json  ✅ T2V distilled (GGUF Q4 + connector, LoRA 없음)
│   │       └── i2v_ltx2_distilled.json  ✅ I2V distilled (동일 구성)
│   └── renderer/
│       ├── composer.py                  ✅ 진입점
│       ├── layout.py                    ✅ 오케스트레이터 (concat 후 seg 즉시 정리)
│       ├── _frames.py                   ✅ PNG 프레임 생성 + MD5 오버레이 캐시
│       ├── _tts.py                      ✅ TTS 오디오 합성
│       ├── _encode.py                   ✅ 단일 NVENC 인코딩 (filter_complex 통합)
│       └── thumbnail.py                 ✅
├── llm/                                 ✅ llm-worker Spring Boot 소스 (별도 빌드)
├── uploaders/
│   ├── base.py                          ✅ UploaderRegistry
│   └── youtube.py                       ✅ YouTube Data API v3
├── analytics/
│   ├── collector.py                     ✅ YouTube Analytics 수집
│   └── feedback.py                      ✅ LLM 인사이트 → feedback_config.json
├── dashboard_worker/
│   ├── main.py                          ✅ Job 폴링 루프
│   └── handlers.py                      ✅ JobType별 핸들러 (TTS_PREVIEW synthesize 사용)
├── monitoring/
│   ├── alerting.py                      ✅
│   └── daemon.py                        ✅
├── test/
│   └── test_e2e_structure_improve.py    ✅ 21 unit + 5 integration 테스트
└── pytest.ini                           ✅ 마커 등록
```

---

## ⬜ 선택 구현 / 미완료

### telegram-bridge (`telegram/`)

WaggleBot 파이프라인 제어 + 파일관리/Git/알림 브리지. 구현 완료.

```
telegram/
├── Dockerfile               ✅
├── src/
│   ├── bot/command-handler.ts  ✅ /status, /posts, /approve, /reject, /crawl + 파일/Git 명령
│   ├── bot/keyboard.ts         ✅ MainMenu 파이프라인 버튼 포함
│   ├── pipeline/
│   │   ├── wagglebot-api.ts    ✅ Spring Boot API 클라이언트
│   │   └── pipeline-commands.ts ✅ 파이프라인 명령 처리
│   ├── notification/           ✅ 알림 발송
│   └── scheduler/              ✅ 일일 브리핑
└── config.ts                   ✅ BACKEND_URL 지원
```

---

## 버그 픽스 이력 (2026-06-11 기준)

| 배치 | 커밋 | 주요 수정 |
|------|------|------|
| 1차 | `0d2162f` | SceneDirector mood 미전달 3곳, _MOOD_TO_STYLE 9종 확장, LlmLog 복합 필터, HD_RENDER ImportError |
| 2차 | `a96cdfc` | TTS 캐시 손상 폴백, 0-duration 프레임 필터, post None 검사, 타이머 누수 |
| 3차 | `c655a4b` | TTS URL 오독, subprocess timeout, hash 충돌, migration DDL 원자성, llm-logs 경쟁 조건 |
| 4차 | `6b5c20d` | HD 렌더 중복 방지, mood_weights 피드백 주입, ComfyUI 워크플로우 mtime 캐시 |
| 5차 | `913e606` | WP-1~8 전체: TTS 프리뷰 ImportError, 비디오 단일 인코딩, 실패 원인 UI, 프롬프트 강화 6종, Fish Speech 워밍업 스킵, Phase 5∥6 병렬, 갤러리 모달, VoiceCatalogService, ai_fitness JSONDecoder, parseProgress camelCase, ProgressController 원자적 retry, HD 렌더 voice_key, _handle_upload commit 누락 |
| 6차 | `7f4904c` | 모바일 햄버거, 갤러리 페이지네이션, 비디오 프롬프트 버그 + e2e 15개 |
| 7차 | `bc269b6` | 수신함 일괄 승인/거절/크롤링 API 에러 핸들링 누락 |
| 8차 | `3df1358` | 에디터 상세 페이지 API 에러 핸들링 누락 |
| 9차 | `5290f78` | processor.py use_content_processor fresh config 읽기 (frozen cfg 버그) |
| 10차 | `ec4a28d` | normalizer.py 컨테이너 경로(parents[3]→[2])·max_chars 계산 버그, ab_test.py 경로 버그 |
| 11차 | `ed9f9e8` | analytics/feedback.py mood_weights 레거시 키(shocking/funny…) → 9-mood 시스템 교체 |

## 다음 개선 우선순위

현 상태로 전체 파이프라인이 동작 가능. 주요 선택적 개선 항목은 모두 완료됨.

### 장기 개선 후보 (미구현)

| 항목 | 설명 |
|------|------|
| 크롤러 사이트 추가 | 인스티즈, 더쿠, MLB파크 등 (ADDING_CRAWLER.md 참조) |
| VRAM 누수 모니터링 | 장기 운영 시 nvidia-smi 주기적 로그 + 임계치 경보 |
| 대시보드 다크모드 | Sidebar 토글 버튼 연결 (ThemeProvider 미구현) |
| 크롤러 트레이 알림 | 크롤링 시 중요 게시글 즉시 텔레그램 알림 |
