# prompt-upgrade

## 0. 실게시글 E2E 검증 결과 (post 9999910 — 추가 검증 라운드)

**APPROVED → PREVIEW_RENDERED 완주.** 최종 영상: `media/video/nate_pann/post_375458175_SD.mp4` (1080×1920, h264+aac, 64.5초). 프레임 추출로 비디오 씬이 레이아웃에 자막과 함께 합성됨을 육안 확인.

**V3 핵심 기능 실전 검증:**

| 항목 | 결과 |
|------|------|
| 씬 구성 | 22씬 = T2V 7 + 정적 15 (I2V 0 — 게시글 이미지가 적합성 필터 미통과, 정상) |
| 비주얼 앵커 | 1회 생성(342자) — "30대 후반 남성 멘토·휴게실·20대 여성 후배"가 **모든 T2V 씬 프롬프트에 일관 반영** (모션 아크 "걱정→상처→억눌린 분노" 포함) |
| 검증 체인 | 재시도 회복 2건(too_long, question_mark) + 결정적 폴백 1건(korean_text) — **메타 응답 유출 0건** |
| 클립 생성 | **7/7 전부 attempt-1 성공**, 재시도·폴백 병합 0 (distilled, 클립당 ~2.6분) |
| 클립 길이 | ffprobe 실측: 97~121프레임 = **4.04~5.04초** (전부 1+8k, 145 캡 이내) — 97 초과 프레임(113·121) 정상 생성으로 "4초 고정+루프" 문제 해소 실증 |
| call_type 라우팅 | LLMLog 분리 기록: `video_prompt_t2v` 10(7씬+재시도3) · `video_prompt_simplify` 7 · `video_visual_anchor` 1 (기존엔 전부 "raw") |

**E2E 관찰 반영 튜닝 (테스트 39 passed):**
- `too_long` 상한 1200→**1600자** — 장황하지만 정상인 프롬프트를 폴백으로 버리지 않게
- `_RETRY_HINTS` 신설 — 실패 사유별 재시도 보강 지시(한글 포함→"한국어 인용 금지" 등)

**E2E 중 발견·수정한 기존 파이프라인 결함 2건 (V3와 무관, E2E 차단 요인):**
1. `config/settings.py` `FISH_SPEECH_TIMEOUT` 120→**300초** — 리텐션 개편 후 대본 600자+(9문장) 전체 TTS 합성이 문장당 ~13초로 120초 초과 → ReadTimeout·재시도 중복 큐잉 악순환
2. `core/processor.py` `llm_tts_stage`에 **MariaDB errno 1020 방어** — `mariadb:11` 롤링 태그가 11.8.8로 올라오며 `innodb_snapshot_isolation=ON`이 기본화. 수십 분 트랜잭션 동안 `stamp_progress`가 별도 세션으로 갱신한 `contents` 행을 오래된 스냅샷으로 UPDATE → **결정론적 1020**. render_stage(L903)에 이미 있던 `session.rollback()` 패턴을 llm_tts_stage 최종 저장 직전에 미러링

**남은 개선 후보 (이번 범위 외):** 씬 0 클립에서 over-shoulder 극전경 얼굴이 만화풍으로 렌더됨 — distilled 8-step 한계. 템플릿 PERSON FALLBACK이 이미 극단 클로즈업을 기피하지만, "전경에 얼굴을 크게 두는 over-shoulder" 자체를 회피 지시에 추가하는 보강 여지 있음.

---

## 1. 작업 결과

LTX-2 비디오 프롬프트 엔진 V3 전면 개편 + 클립 길이 4~6초 정책. 목표: 대본·첨부 이미지에 맞는 자연스러운 4~6초 클립으로 지속시청시간 강화.

- **연속성**: post당 1회 비주얼 앵커(주인공 외모·복장+장소) 생성 → 전 T2V 씬 공유 → 클립 간 인물·배경 일관성 확보
- **I2V 이미지 인지**: `call_llm(images=)` vision 신설(api 백엔드) — 초기 이미지를 haiku vision으로 분석한 brief를 모션 프롬프트에 주입. 실패 시 image_filter category 힌트 폴백
- **메타 응답 유출 차단**: 실측 유출 사례("I'm Kiro, an AI assistant...", 되물음)를 검증→1회 재시도→mood별 결정적 폴백으로 차단
- **동적 길이**: "4-second" 하드코딩 제거, 씬 병합 4.0~6.0초 + 프레임 상한 145(6.04s@24fps, ADR-0004)
- **버그 픽스**: `call_ollama_raw`(call_type="raw") 경유로 무력화돼 있던 `video_prompt_*` 모델 라우팅·오버라이드 정상화
- 전체 테스트 **203 passed, 0 failed** (기존 155 → 신규 48개 추가 + 스테일 1건 동기화), 실 LLM 스모크 5건 통과

## 2. 수정 내용

### `worker/ai_worker/llm/transport.py`
- `call_llm(..., images=[Path|str])` — api 백엔드는 base64 image block(이미지→텍스트 순), cli 백엔드는 경고 후 무시
- `_encode_image_blocks()` (jpeg/png/webp/gif, 5MB 초과·누락 skip), `llm_backend_supports_vision()`
- `_CALL_TYPE_MODEL_MAP`에 `video_visual_anchor`/`video_image_brief` → haiku

### `worker/ai_worker/video/prompt_engine.py` (핵심, V3)
- **템플릿**: `_T2V_SYSTEM_V3`/`_I2V_SYSTEM_V3` — 무치환 정적 system(api 프롬프트 캐싱 적중) + 동적 user prompt 분리. 모션 아크(시작→전개→끝+미해결 비트), 비주얼 앵커 재사용, 직전 씬 프레이밍 회피, 조각 문장 허용·되물음 금지 출력 규칙
- **신설 메서드**: `generate_visual_anchor()`(post당 1회, 실패 시 ""), `generate_image_brief()`(vision, 실패 시 None → post 단위 비활성)
- **검증 체인**: `_validate_prompt()`(한글/물음표/메타 마커/길이) → `_RETRY_SUFFIX` 재시도 1회 → `_FALLBACK_PROMPTS`(mood 9종) / `_FALLBACK_I2V` — generate_prompt는 예외를 던지지 않음
- `generate_batch()` 시그니처 불변 — core/processor·content_processor 두 호출 경로 무수정 적용(ADR-0003 보존)
- `simplify_prompt(visual_anchor=)` — 재시도용 프롬프트에도 주인공·장소 유지
- 호출 전부 `call_llm` 직접 + 정확한 call_type (기존: `call_ollama_raw` → "raw"로 라우팅 무력화)

### 길이 정책 (4~6초)
- `worker/ai_worker/scene/settings.yaml`: `target_clip_duration` 3.5/5.0 → **4.0/6.0** (실효 지점, lru_cache라 worker 재시작 필요)
- `worker/ai_worker/scene/director.py`: `generate_merge_candidates*` 기본값·`_llm_direct_body` default 동기화
- `config/settings.py`: `VIDEO_NUM_FRAMES_MAX = 145` 신설
- `worker/ai_worker/video/manager.py`: `calc_frames_from_duration(..., max_frames=)` 캡 — oversized 씬(>6초) OOM 폭주 방지
- `core/processor.py`·`pipeline/content_processor.py`: video_config에 키 1개 추가

### 이미지 category 플럼빙
- `SceneDecision.video_image_category` 신설 — `_convert_to_scene_decisions()` itv 2분기 + `assign_video_modes()`에서 image_filter category 저장 (I2V vision 폴백 힌트)

### `config/video_styles.json`
- 9 mood 전면 재작성 — 실사 촬영 가능 단서만. 편집 효과(freeze frame/speed ramp/glitch/split-screen/strobing)·fish-eye·whip pan/crash zoom 제거 (REALISM 블록·CAMERA RULE 충돌 해소)

### 테스트
- `worker/test/test_prompt_engine.py`: 전면 개편 — 실 LLM 게이트 프로브를 `call_llm` 핑으로 교체(V3는 폴백 반환이라 기존 프로브 무의미), mock 테스트 37개(검증/재시도·폴백/동적 블록/앵커/brief/vision 비활성/transport image block) + Live 5개
- `worker/test/test_video_manager.py`: `VIDEO_NUM_FRAMES_MAX` config + 프레임 캡 3개
- `worker/test/test_llm_scene_director.py`: category 플럼빙 3개
- `worker/test/test_e2e_structure_improve.py`: 스테일 1건 동기화 — 50d62ef(떡밥 구체화)가 프롬프트 문구를 압축형으로 바꿨는데 테스트 기대값 미갱신이던 **기존(HEAD) 실패** 수정

## 3. 테스트 결과물 위치

```
docker compose exec ai_worker python -m pytest test/ -q
→ 203 passed, 3 skipped  (실패 0)
```
- 실 LLM 생성 샘플: `worker/test/test_prompt_engine_output/all_moods_prompts.txt` (9 mood V3), `generated_prompts.txt`(humor/horror V3 append), `visual_anchor.txt` (앵커 샘플)
- V3 실측: 메타 응답 0건, 앵커가 사연(며느리·시어머니·명절 거실)에 정확 부합

## 4. 수동 테스트 방법

```bash
# 1) 단위+mock (LLM 불필요)
docker compose -f env/docker-compose.yml exec ai_worker \
  python -m pytest test/test_prompt_engine.py -k "not Live" -v

# 2) 실 LLM 스모크 (9 mood 재생성)
docker compose -f env/docker-compose.yml exec ai_worker \
  python -m pytest test/test_prompt_engine.py -k "Live" -v

# 3) 파이프라인 E2E: VIDEO_GEN_ENABLED=true + APPROVED 게시글 1건 처리 후
docker compose -f env/docker-compose.yml logs --tail 100 ai_worker
#   확인 포인트: "[prompt] 비주얼 앵커 생성 완료", "[prompt] batch 완료: ... brief 성공=n",
#   Phase 7 프레임 수 ≤145, media/tmp/videos 클립 길이 4~6초
# 4) LLMLog에서 call_type별 기록 확인 (라우팅 정상화 검증):
#   video_prompt_t2v / video_prompt_i2v / video_visual_anchor / video_image_brief
```

**배포 노트**: `scene/settings.yaml`은 lru_cache — 적용에 ai_worker 재시작 필요.

## 5. 추천 commit message

```
feat: LTX-2 비디오 프롬프트 V3 — 앵커 연속성·I2V vision·검증 폴백 + 클립 4~6초(ADR-0004)
```

## 6. DOC-MAP 기준 갱신한 문서 목록

- `CLAUDE.md` — LTX-2 프레임 제약 9~97 → 9~145 + ADR-0004 링크
- `docs/adr/0004-clip-4-6s-frames-145.md` — 신설
- `docs/pipeline.md` — Phase 4.5(category)/Phase 6(V3 흐름)/Phase 7(동적 프레임·폴백 다이어그램)/LLM 라우팅(call_type 5종·vision)
- `docs/config.md` — VIDEO_NUM_FRAMES_MAX, llm_model_overrides 실제 call_type 키 교정, video_styles.json 구조 계약·작성 원칙, FISH_SPEECH_TIMEOUT 120→300
- `docs/DOC-MAP.md` — ADR 현황 표에 0004
- `docs/implementation-status.md` — 본 작업 기록 + 실게시글 E2E 결과 + 파이프라인 결함 2건 수정 이력
