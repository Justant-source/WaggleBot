# prompt-engine-v3

## 1. 작업 결과

LTX-2 비디오 프롬프트 엔진을 V3로 전면 개편. 지속시청시간 강화를 위한 5가지 핵심 개선.
전체 테스트 203 passed (신규 48개 포함), 0 failed.

## 2. 수정 내용

### `worker/ai_worker/video/prompt_engine.py` (V3 전면 개편)

**연속성 — 비주얼 앵커:**
- `generate_visual_anchor()` 신설: post당 1회 haiku로 주인공 외모·복장+장소 2~3문장 생성
- `generate_batch()`에서 T2V 씬이 있으면 앵커 생성 → 모든 T2V 씬 user prompt에 주입
- `simplify_prompt(visual_anchor=)` 추가: simplified 프롬프트에도 앵커 유지 지시

**I2V vision brief (api 백엔드 전용):**
- `generate_image_brief()` 신설: `call_llm(images=[Path])` — base64 이미지 블록으로 haiku vision 분석
- 초기 이미지 내용 1~2문장 분석 후 I2V 프롬프트에 주입 (모션이 피사체와 모순 방지)
- 첫 실패 시 post 내 vision 비활성 + `SceneDecision.video_image_category` 힌트 폴백

**출력 검증 + 결정적 폴백:**
- `_validate_prompt()`: 한글/물음표/메타 마커/길이 검증
- 실패 → 1회 재시도(강화 suffix) → 재실패 → mood별 결정적 폴백 9종
- 파이프라인 중단 없음 — 모든 오류 흡수

**동적 클립 길이:**
- "4-second" 하드코딩 → `estimated_tts_sec` 4~6초 클램프(`_clamp_duration`)로 교체
- user prompt에 `Clip duration: about {X} seconds` 동적 주입

**기타:**
- `call_ollama_raw` → `call_llm(call_type=video_prompt_t2v/i2v/...)`으로 교체 (정확한 라우팅)
- `system/user 분리 + cache_prefix=True` — api 백엔드 프롬프트 캐싱
- 샷 다양성: 직전 씬 프레이밍 추출 후 다음 씬에 "use a different framing" 주입
- 모션 아크(시작→전개→끝+미해결 비트) 지시 추가

### `worker/ai_worker/llm/transport.py`
- `call_llm(images=)` 파라미터 추가 (api 백엔드만 처리, cli는 경고 후 무시)
- `_encode_image_blocks()`: 로컬 이미지 → base64 Messages API content block 변환
- `llm_backend_supports_vision()` 헬퍼 추가
- `_CALL_TYPE_MODEL_MAP`에 `video_visual_anchor`, `video_image_brief` (haiku) 추가

### `worker/ai_worker/video/manager.py` + `config/settings.py`
- `calc_frames_from_duration(max_frames=)` 파라미터 추가 → ADR-0004 상한 적용
- `VIDEO_NUM_FRAMES_MAX = 145` 추가 (1+8×18 = 6.04초 @24fps)
- `content_processor.py` · `processor.py` 양쪽 config dict에 `VIDEO_NUM_FRAMES_MAX` 전달

### `config/video_styles.json`
- 9 mood 모두 V3 실사 단서로 재작성: 편집 효과(freeze frame/speed ramp/glitch)·반실사 렌즈(fish-eye)·과격 무브(whip pan/crash zoom/snap zoom) 전량 제거
- `test_prompt_engine.py::test_video_styles_no_anti_realism_cues` 가드로 회귀 방지

### `worker/ai_worker/scene/settings.yaml`
- `target_clip_duration min: 3.5 → 4.0, max: 5.0 → 6.0` (ADR-0004와 동기)

### `config/settings.py`
- `FISH_SPEECH_TIMEOUT`: 120 → 300초 (V3 대본 600자+ 합성 시간 초과 방지)

### `worker/ai_worker/scene/director.py`
- `SceneDecision.video_image_category` 필드 추가 (I2V vision brief 폴백용)
- `_convert_to_scene_decisions()`·`assign_video_modes()` — itv/oversized 씬 선정 시 category 저장
- `generate_merge_candidates()` 기본값 min/max를 4.0/6.0으로 동기

### `docs/`
- `docs/adr/0004-clip-4-6s-frames-145.md` 신규 (ADR)
- `docs/pipeline.md`, `docs/config.md`, `docs/implementation-status.md`, `CLAUDE.md`, `docs/DOC-MAP.md` 갱신

## 3. 테스트 결과

```
203 passed, 3 skipped, 0 failed
신규: TestValidatePrompt(7), TestHelpers(3), TestRetryAndFallback(5), TestPromptComposition(5),
      TestGenerateBatch(6), TestTransportVision(7), TestStaticAssets(4),
      TestConvertToSceneDecisions +3(category), TestVideoManager +3(frame cap)
```

## 4. 수동 테스트 방법

```bash
docker compose exec ai_worker python -m pytest test/ -q
```

## 5. 추천 commit message

```
feat: LTX-2 프롬프트 엔진 V3 + 클립 4~6초 정책 (ADR-0004)
```

## 6. DOC-MAP 기준 갱신한 문서 목록

- `docs/pipeline.md` — Phase 6 V3 상세
- `docs/config.md` — VIDEO_NUM_FRAMES_MAX, video_styles.json 구조 계약
- `docs/implementation-status.md` — V3 개편 이력
- `docs/adr/0004-clip-4-6s-frames-145.md` — 신규 ADR
- `docs/DOC-MAP.md` — ADR-0004 항목 추가
- `CLAUDE.md` — LTX-2 프레임 범위 9~145 갱신
