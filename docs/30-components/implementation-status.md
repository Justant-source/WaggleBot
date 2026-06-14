# WaggleBot — 구현 현황

> **last-verified:** 2026-06-13 (p5-chat-capture)
> **scope:** 구현 완료·미완료 현황, 버그 픽스 이력

현재 코드베이스의 구현 완료/미완료 상태 정리. (2026-06-11 기준)

## 전체 현황 요약

전체 파이프라인(크롤링→AI 처리→렌더링→업로드) 구현 완료. 대시보드 UI·REST API·Python 워커 전체 운영 가능.

| 서비스 | 상태 | 비고 |
|--------|------|------|
| `llm-worker` | ✅ 완전 구현 | Claude CLI 게이트웨이 |
| `backend` | ✅ 완전 구현 | 전체 Controller + Domain + Service |
| `frontend` | ✅ 완전 구현 | 7개 어드민 페이지 + 공용 컴포넌트 |
| `worker/crawlers` | ✅ 완전 구현 | **7개** 사이트 플러그인 + 플러그인 매니저 + Telegram 트레이 알림 |
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
│   ├── instiz.py                        ✅ 인스티즈 실시간 베스트
│   ├── theqoo.py                        ✅ 더쿠 HOT 게시판
│   ├── mlbpark.py                       ✅ MLB파크 불펜+자유게시판
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

## ✅ 선택 구현 완료

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

## TTS OpenAudio S1-mini 업그레이드 (2026-06-12, ADR-0005)

| 영역 | 변경 |
|------|------|
| 모델/서버 | Fish Speech 1.5.1 → OpenAudio S1-mini, server-cuda 이미지 digest 고정, env 기반 체크포인트 오버라이드, curl healthcheck, start_period 180s. `scripts/download_openaudio_s1.sh`(gated HF) 신규 |
| 참조 음성 | base64 평면파일 → `reference_id` 폴더 구조(`assets/voices/<key>/NN.wav+NN.lab`) + memory cache. voices.json v2(ref_dir/params). assets/voices를 UID 1000 소유로 (validate_env) |
| 클라이언트 | `fish_client.py` 재작성: 참조 해석 체인, 감정 마커 주입, 장문 분할·concat, WAV 헤더 길이검증, loudnorm+aresample 후처리. `language` 필드 제거, top_p/normalize 추가 |
| 정규화 | `normalizer.py`: 슬랭 로더 merge 버그 수정, 조사 교정 슬랭 경계 한정(마을→마를 회귀 해결), 숫자 확장(소수/콤마/범위/유월·시월/단위/전화), 영문 약어 별도 패스+내장 사전(CCTV/SNS/AI 등, assets/는 gitignore라 코드 내장), ㅋㅋ→(laughing) 게이트 |
| 감정 배선 | content_processor·layout·_tts·dashboard handlers에 `emotion=scene.tts_emotion` 전달. `TTS_EMOTION_MARKERS` 신규(EMOTION_TAGS와 별개 축) |
| 음성 등록 | `worker/tools/prepare_voice.py` 신규(faster-whisper 자동 전사). requirements에 faster-whisper |
| 테스트 | `test_tts_normalizer.py` 신규(29 케이스, 오프라인 통과), `test_fish_speech.py` 재작성(URL 버그 수정, synthesize 통합 경로) |

> ⚠ **라이브 검증(A3) 미완료** — gated 모델 다운로드(사용자 HF 인증) 후 fish-speech 교체 필요.
> 실측 VRAM/RTF·WAV 샘플레이트·reference_id 동작은 최초 기동 시 확인 (ADR-0005 미해결 항목).
| 11차 | `ed9f9e8` | analytics/feedback.py mood_weights 레거시 키(shocking/funny…) → 9-mood 시스템 교체 |

### 대본 리텐션 프롬프트 개편 (2026-06-11)

쇼츠 시청 지속(리텐션) 강화를 위한 Sonnet 대본 프롬프트 개선 + 활성 경로 입력 격차 수정:

- **프롬프트(§2 리텐션 설계 전면 개편)**: `chunker.py`·`client.py` 양쪽에 Hook 강화(구체명사/숫자·첫어절 강조·1인칭 고백형 추가), Hook-Payoff 계약(답은 마지막 1/3), 에스컬레이션 체인, 블록 클리프행어, 감정 낙차, 편가르기/루프형 Closer, 출력 전 자가점검 추가. few-shot 예시를 리텐션 곡선 시범으로 교체. 자극은 내용으로, 표현 순화 원칙 유지.
- **입력 격차 수정 (활성 경로)**: `chunk_with_llm()`이 제목·베스트 댓글·성과 피드백을 받지 못하던 결함 수정 → `type=comment` 인용 씬과 피드백/A/B 루프 부활. 본문 절단 2000→4000자 통일, temperature 0.7.
- **공통화**: `analytics.feedback.build_extra_instructions()` 신설(피드백+A/B 조립), `call_llm_json` temperature 파라미터 추가.
- 검증: 기존 32 테스트 + 신규 `test_chunker_retention.py` 6개 통과, 실게시글(post_id=71) E2E로 리텐션 구조·댓글 부활·길이 제약 확인.
- **후속 보정(실게시글 QA 반영)**: ① 중간 떡밥 문구를 mood별 2~3개 톤 예시 + "복붙 금지"로 다양화(anger 게시글끼리 같은 문구 쏠림 완화) ② 실존 개인 식별정보(실명·나이·연락처·상세주소) 익명화 규칙 추가 — 사건·사고·의료·법적 분쟁 글에서 '누구인지'만 가리고 서사·사실관계는 보존. chunker.py·client.py 동기.
- **2차 후속 보정**: ③ 떡밥 구체화 강제 — "지금부터예요" 류 막연한 마무리 금지, 사연 구체 단어(인물·사물·반전 대상) 주입((X)/(O) 예시). 잔여 수렴(8건 중 3건 동일) 해소 확인 ④ 약자 학대 편가르기 제외 — 아동·노약자·동물 대상 명백한 학대·폭력은 찬반 투표형 closer 금지("훈육이냐 학대냐" 식), 피해자 보호·공감 관점 질문으로 대체. chunker.py·client.py 동기.

### LTX-2 비디오 프롬프트 V3 개편 + 클립 4~6초 (2026-06-11)

지속시청시간 강화를 위한 Phase 6 프롬프트 엔진 전면 개편 (`prompt_engine.py` V3):

- **연속성**: post당 1회 비주얼 앵커(주인공 외모·복장+장소, haiku) 생성 → 전 T2V 씬 공유로 클립 간 인물·배경 일관성. simplified 프롬프트에도 앵커 유지 지시.
- **I2V vision brief**: `call_llm(images=)` 신설(api 백엔드 전용, base64 image block) — 초기 이미지 내용을 haiku vision으로 분석해 모션이 피사체와 모순되지 않게 함. 실패 시 post 단위 비활성 + `SceneDecision.video_image_category`(image_filter 분류, 신규 플럼빙) 힌트 폴백.
- **출력 검증+폴백**: 메타 응답 유출 차단(`_validate_prompt`: 한글/물음표/메타 마커/길이) → 1회 재시도 → mood별 결정적 폴백. 실측 유출 사례("I'm Kiro...") 픽스처로 테스트 가드.
- **동적 길이**: "4-second" 하드코딩 제거 → `estimated_tts_sec` 4~6초 클램프 주입. 씬 병합 4.0~6.0초(`scene/settings.yaml`), 프레임 상한 `VIDEO_NUM_FRAMES_MAX=145` → [ADR-0004](../90-adr/0004-clip-4-6s-frames-145.md).
- **기타**: `call_ollama_raw`(call_type="raw") → `call_llm`(정확한 call_type) 전환으로 모델 라우팅·오버라이드 정상화, system/user 분리 + `cache_prefix=True`로 api 프롬프트 캐싱, 모션 아크(시작→전개→끝+미해결 비트)·직전 씬 프레이밍 회피(샷 다양성) 지시, `video_styles.json` 9 mood 실사 단서로 재작성(편집 효과·반실사 렌즈 제거), 스토리 컨텍스트(제목+body_summary) 주입.
- 검증: 전체 스위트 203 passed (신규 48개: 검증/재시도/앵커/brief/vision 전송/프레임 캡/category 플럼빙), 실 LLM 스모크 5건 통과 — V3 출력에서 메타 응답 0건, 앵커가 사연(며느리·시어머니·명절 거실)에 정확 부합.
- **실게시글 E2E (post 9999910, 사내 스토커 누명 사연)**: APPROVED→PREVIEW_RENDERED 완주. 22씬(T2V 7, 정적 15), 클립 7/7 attempt-1 성공, 프레임 97~121(4.04~5.04초, 145 캡 이내), 앵커→씬 일관성 실증(휴게실·30대 남성·여성 후배가 전 씬 공유), call_type별 LLMLog 분리 기록 확인. 검증 체인 실전: 재시도 회복 2건(too_long·question_mark), 결정적 폴백 1건(korean_text) — 메타 유출 0. E2E 관찰 반영 튜닝: too_long 1200→1600자, 실패 사유별 재시도 힌트(`_RETRY_HINTS`).
- **E2E 중 발견·수정한 파이프라인 결함 2건 (V3와 무관한 기존 버그)**: ① `FISH_SPEECH_TIMEOUT` 120→300초 — 리텐션 개편 후 대본 600자+ 전체 TTS 합성(문장당 ~13초×9)이 120초 초과 → 타임아웃·중복 큐잉 악순환 ② `llm_tts_stage` 종료 시 MariaDB errno 1020 — `mariadb:11` 롤링 태그가 11.8.8로 올라오며 `innodb_snapshot_isolation=ON` 기본화, 수십 분 트랜잭션 중 stamp_progress가 갱신한 contents 행을 오래된 스냅샷으로 UPDATE → 결정론적 실패. render_stage(L903)와 동일한 `session.rollback()` 패턴을 `processor.py` llm_tts_stage에 적용.

### 다크모드 + pytest 컬렉션 픽스 (2026-06-12)

- **다크모드**: `next-themes` ThemeProvider 연결 (`app/providers.tsx` 신규, `app/layout.tsx` 적용). 어드민 셸 3개(`AdminTopBar`, `AdminSidebar`, `AdminShell`) 하드코딩 색상(`bg-white`, `text-gray-*`, `border-gray-200` 등)을 CSS 변수 기반 Tailwind 시맨틱 클래스(`bg-background`, `text-foreground`, `border-border`, `text-muted-foreground`, `hover:bg-accent`)로 전환. `tailwind.config.js`의 `darkMode: ['class']`는 이미 설정되어 있었음. 활성 내비 항목에 `dark:bg-blue-900/30 dark:text-blue-300` 추가.
- **VRAM 누수 모니터링**: `config/monitoring.py`에 `GPU_VRAM_WARNING=85`, `GPU_VRAM_CRITICAL=95` 추가. `worker/monitoring/alerting.py`의 GPU 체크 블록에 VRAM % 임계치 알림 추가 — WARNING은 로그 경고("누수 의심"), CRITICAL은 이메일+슬랙 발송. `worker/monitoring/daemon.py` 헬스 로그에 VRAM% 포함.
- **pytest 컬렉션 픽스**: `worker/test/conftest.py`에 `test_fish_speech.py` 추가 — `async def test_*()` 함수를 `asyncio.run(main())`으로 직접 호출하는 라이브 통합 테스트 구조로 pytest-asyncio 없이 수집하면 실패. (`test_pipeline_phases.py`와 동일 패턴)

### 크롤러 사이트 추가 + Telegram 트레이 알림 (2026-06-12)

- **신규 크롤러 3종**: `instiz.py`(인스티즈 실시간 베스트), `theqoo.py`(더쿠 HOT, XE 기반), `mlbpark.py`(MLB파크 불펜+자유게시판). `@CrawlerRegistry.register()` 플러그인 패턴 준수 — `ENABLED_CRAWLERS`에 추가하면 즉시 동작.
- **Telegram 트레이 알림**: `BaseCrawler._notify_tray()` 신규. 신규 게시글 저장 시 점수 ≥ `TELEGRAM_ALERT_THRESHOLD`(기본 100점) 또는 자동승인이면 telegram-bridge hook(`:3847/hook`)에 `notification` 이벤트 POST. `TELEGRAM_CRAWL_ALERT=false`(기본)로 비활성, `.env`에서 `true`로 전환. `docker-compose.yml` crawler 서비스에 환경변수 3개 추가.

### 크롤러 4종 파서 수정 (2026-06-13)

- **dcinside.py**: 출처 regex greedy 변경 + `[원본 보기]` 제거 + 이미지 전용 글 보완 로직
- **instiz.py**: Brotli 압축 미지원 수정 + parse_post 셀렉터 교정
- **mlbpark.py**: tbl_type01/t_left/view_context/reply_list 셀렉터 교정
- **theqoo.py**: Rhymix HTML 구조 대응 + 댓글 AJAX API 교체 (`dispTheqooContentCommentListTheqoo`)
- **crawler.py**: Accept-Encoding에서 `br` 제거(brotli 패키지 미설치 환경 대비)
- `test_crawlers_e2e.py` E2E 테스트 추가

### LLM JSON 파싱 견고화 + DECLINED 분기 (2026-06-13)

- `transport.py` `extract_json_object`: 코드 펜스 제거 + 모든 `{` 위치에서 raw_decode — 프록시가 ```json 펜스·prose를 붙이는 경우 hook 누락 ValueError → FAILED를 방지
- `LLMContentRefusalError` 신규 — 콘텐츠 거부는 DECLINED로 분기(재시도 차단)
- `main.py` `_mark_post_declined` 신규; llm_tts_worker에서 거부 예외 포착 → DECLINED 마킹
- `scene_director` max_tokens 2048→4096 (씬 다수 잘림 방지)
- `test_llm_json_robust.py` 신규

### 다화자 TTS 자동 배정 (2026-06-13)

- `voices.json` v3: gender/age_range 메타데이터 + 음성 24개(19개 신규)
- `voice_assigner.py` 신규: `pick_voice(gender, age, exclude)` — 성별 우선·연령 근접 선택
- `chunker.py`: narrator_gender/age + speaker/character 화자 태깅 스키마 추가
- `ScriptData.narrator_voice` 필드 추가 — `llm_tts_stage` → `render_stage` SceneDirector까지 전달
- `content_processor.py`·`processor.py` 양쪽 SceneDirector에 narrator_voice 배선

### 와글 브랜드 숏폼 레이아웃 v3 (2026-06-13)

Claude Design 핸드오프 기반으로 렌더러 전면 교체. 컨테이너 PNG 테스트 ALL PASS.

| 항목 | 내용 |
|------|------|
| **P1 핵심 비주얼** | 옐로우 헤더 `#FBD024` h150 + 코드드로잉 제목블록(메타줄·구분선) + 굵은 검정 자막(흐림 제거) + 자연비율 contain 이미지 |
| **P2 아웃트로** | 마스코트(PIL 코드드로잉) + 참여유도 질문 5종 + 댓글입력창 목업 (구독유도 제거) |
| **P3 영상 자연비율** | `_render_video_segment` ffprobe → contain 계산 → `force_original_aspect_ratio=decrease` |
| **P4 댓글 씬** | `SceneType="comments"` 신규 + `comment_items` 필드 + DB 원본 likes 직접 전달 + `_render_comments_frame` |
| **P5 대화 캡처** | `SceneType="chat"` + `_render_chat_frame` (is_mine 기준 좌/우 버블, 아바타, 발신자명) + chunker `chat_messages` 추출 + ScriptData 직렬화 + 전 processor 경로 배선 |
| **기타** | `_title_block_bottom_y()` 순수헬퍼(가변 제목 높이 일원화) · `_fmt_count`/`_relative_time` 유틸 |

## 다음 개선 우선순위

현 상태로 전체 파이프라인이 동작 가능. 레이아웃 v3 + P1~P5 씬타입 전부 완료됨.
