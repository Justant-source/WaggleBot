# TTS 실제 시간 기반 씬 병합 + 최소 비디오 보장 + I2V 임계값 완화

## 1. 작업 배경 및 목적 (Context & Objective)
- **이슈 1:** 편집실 확정 후 씬 병합 시 글자수 기반 TTS 시간 추정(4자/초)이 부정확하여 비디오 클립 길이가 실제 발화와 불일치
- **이슈 2:** Post 3024의 I2V 미사용 원인 조사 + 일반적인 I2V 임계값 완화
- **이슈 3:** Post 2180 — 모든 body 씬이 5초 초과 시 merge_groups가 비어서 비디오 클립이 0개 할당되는 문제
- **작업 목적:**
  - Phase 4 이전에 Fish Speech TTS 실제 실행 → 정확한 발화 시간으로 씬 병합 결정
  - 모든 씬이 oversized여도 max_video_clips까지 비디오 클립 강제 보장 (5초 영상 루프 재생)
  - I2V 임계값 0.6→0.45 완화

## 2. 핵심 작업 결과 (Core Achievements)
- Phase 4-pre 도입: Phase 4 이전에 모든 body 텍스트의 Fish Speech TTS를 사전 생성
- 실제 TTS 발화 시간으로 씬 병합 후보(generate_merge_candidates) 계산
- Phase 5에서 사전 생성 TTS 재사용 (intro/outro만 신규 생성 → 처리 시간 증가 없음)
- Phase 4-D `_ensure_video_clips()`: max_video_clips까지 비디오 승격 (균등 분포, 댓글 제외)
- Post 3024: `images: null` — 이미지가 아예 없는 게시글이라 I2V 사용 불가 (기준과 무관)
- I2V 임계값 0.6→0.45 완화 (settings.py + settings.yaml)

## 3. 상세 수정 내용 (Detailed Modifications)

### `ai_worker/scene/analyzer.py`
- `get_audio_duration(path)` 추가: ffprobe 기반 실제 오디오 재생 시간 측정

### `ai_worker/pipeline/content_processor.py`
- **Phase 4-pre 추가** (기존 Phase 3~4 사이):
  - body 블록별 Fish Speech TTS 실행 + ffprobe 시간 측정
  - `body_tts_map: dict[int, dict]` 생성 (`{index: {audio, duration, voice}}`)
  - 댓글 voice 사전 할당 (Phase 4와 일관성 유지)
  - TTS 실패 시 기존 추정값 폴백
- **Phase 5 수정**: `merged_scene_indices`로 body_tts_map 매핑 → 사전 생성 TTS 재사용

### `ai_worker/scene/director.py`
- `SceneDirector.__init__()`: `body_tts_map` 파라미터 추가
- `direct()`: body_items voice 할당 시 body_tts_map 우선 사용
- `_llm_direct_body()`: 구조 리팩터링 — early return 제거, 모든 경로에서 Phase 4-D 적용
  - scenes_data의 estimated_tts_sec에 실제 TTS 시간 사용
- `_build_llm_input()`: body_tts_map 파라미터 추가, LLM에 정확한 tts_sec 전달
- `_convert_to_scene_decisions()`: body_tts_map으로 실제 시간 적용
- `_all_text_only()`: enumerate + body_tts_map 활용 + merged_scene_indices 설정
- **`_ensure_video_clips()` 신규**: 비디오 클립 수가 max_video_clips에 미달하면 body 씬을 video_text(t2v)로 승격
  - 균등 분포로 선별 (시각적 다양성)
  - 댓글 씬은 승격 대상에서 제외
  - oversized 씬(>5초)도 승격 가능 — 5초 비디오가 TTS 구간 동안 루프 재생

### `config/settings.py`
- `VIDEO_I2V_THRESHOLD: 0.6 → 0.45`

### `ai_worker/scene/settings.yaml`
- `itv_score_threshold: 0.6 → 0.45`

## 4. 하드 제약 및 시스템 영향도 (Constraints & System Impact)
- **VRAM 제약:** 영향 없음 — TTS(Fish Speech ~5GB)는 기존과 동일 시점에 실행
- **처리 시간:** Phase 4-pre에서 TTS 실행 → Phase 5에서 재사용 → **총 처리시간 동일**
- **DB 마이그레이션:** X (불필요)
- **환경 변수 변경:** X
- **의존성 변경:** X

## 5. 엣지 케이스 및 예외 처리 (Edge Cases & Fallbacks)
- Phase 4-pre TTS 실패 시 → `estimate_tts_duration()` 추정값 폴백
- Phase 5에서 사전 생성 TTS 파일 누락 시 → Fish Speech 재호출
- `body_tts_map`이 비어있는 경우 → 모든 경로에서 `estimate_tts_duration()` 폴백
- rule_based 모드(distribute_images) → body_tts_map 미사용 (기존 동작 유지)
- 모든 body 씬이 5초 초과 → `_ensure_video_clips()`가 max_video_clips까지 승격
- LLM 실패 + fallback_on_fail=true → `return None` → distribute_images() 폴백 (비디오 보장은 distribute_images의 1:1 비율로 처리)
- Post 3024 I2V: images가 null이므로 임계값과 무관

## 6. 테스트 및 검증 (Test & Validation)
- **테스트 결과물:**
  - 기존 단위 테스트: `python3 -m pytest test/test_scene_idx_mapping.py test/test_scene_policy.py -v` → 12/12 통과 (sqlalchemy 의존 2개 제외)
  - 문법 검증: 수정 파일 모두 통과
  - Post 2180 시뮬레이션: `_ensure_video_clips(scenes, 5)` → body 10개 중 5개 승격 (씬 1,2,4,6,7), 댓글 0개 승격

- **수동 재현/테스트 스텝:**
  1. `docker compose up ai_worker -d` 재시작
  2. 대시보드 편집실에서 게시글 확정
  3. `docker compose logs --tail 100 ai_worker` 에서:
     - `Phase 4-pre 완료: body TTS 생성=N 실패=M` 로그 확인
     - `최소 비디오 보장: N개 승격` 로그 확인 (oversized 케이스)
     - `Phase 5 완료: TTS 재사용=N 신규=M 실패=0` 로그 확인

## 7. 알려진 문제 및 향후 과제 (Known Issues & TODOs)
- `distribute_images()` (rule_based 모드)의 `estimated_tts_sec`가 여전히 0.0 — LLM 모드에서만 실제 시간 적용
- Phase 4-pre에서 body 블록이 20개 이상일 경우 TTS 생성에 시간 소요 가능 (동일 총 시간이나 Phase 순서 차이)
- I2V 임계값 0.45가 실 운영에서 적절한지 모니터링 필요
- oversized 씬의 5초 비디오 루프 재생은 렌더러(layout.py)에서 이미 지원됨 (video_clip_path + TTS 구간)

## 8. 추천 커밋 메시지 (한글로 작성)
```text
feat: 실제 TTS 기반 씬 병합 + 최소 비디오 보장 + I2V 완화

- Phase 4-pre: Fish Speech TTS 사전 생성 → 정확한 발화 시간으로 씬 병합
- Phase 4-D: _ensure_video_clips() — max_video_clips까지 비디오 승격 (oversized 씬 루프 재생)
- Phase 5: 사전 생성 TTS 재사용 (intro/outro만 신규)
- I2V 임계값 0.6→0.45 완화
```
