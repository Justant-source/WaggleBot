# ADR-0004: 비디오 클립 4~6초 정책 + 동적 프레임 상한 145

> **status:** accepted
> **date:** 2026-06-11
> **related:** worker/ai_worker/scene/settings.yaml, worker/ai_worker/video/manager.py, config/settings.py, docs/pipeline.md

## 컨텍스트

클립 길이 정책이 3.5~5.0초(씬 병합 범위)였고, Phase 7의 동적 프레임 계산
(`calc_frames_from_duration`)에는 **상한이 없었다**:

- 유튜브 쇼츠 지속시청시간 관점에서 4초 미만 클립은 루프 티가 나고
  (FFmpeg `stream_loop`로 TTS 길이까지 반복), 장면 전개가 없어 이탈을 유발했다.
- `scene/settings.yaml`의 `oversized_scene_video: true`로 max 초과 단일 씬도
  비디오 클립이 될 수 있는데, 8초 씬이면 193프레임(8×24→1+8k)을 그대로 시도
  → RTX 3090 lowvram 환경에서 OOM → 4단계 폴백 낭비.

## 결정

1. **씬 병합 범위 4.0~6.0초** — `scene/settings.yaml`의
   `scene_director.target_clip_duration`(min 4.0 / max 6.0)이 실효 지점.
   `director.py`의 함수 기본값(`generate_merge_candidates` 등)도 동기화.
2. **동적 프레임 상한 `VIDEO_NUM_FRAMES_MAX = 145`** (`config/settings.py`) —
   145 = 1+8×18 = **6.04초 @24fps**. `calc_frames_from_duration(..., max_frames=)`
   에서 적용. oversized 씬(>6초)도 클립은 최대 145프레임으로 캡.
3. 프롬프트의 클립 길이 표현도 동적(`_clamp_duration`: 4.0~6.0 클램프) —
   "4-second" 하드코딩 제거 (prompt_engine V3).

CLAUDE.md의 LTX-2 프레임 제약은 `1+8k`(9~145)로 갱신된다.
`video_utils.validate_frame_count()`는 1+8k 격자 보정만 담당하고 상한은
`calc_frames_from_duration`이 담당한다 (책임 분리 — validate에 캡을 넣지 말 것).

## 결과

- 클립이 TTS 길이(병합 4~6초)와 거의 일치 → `stream_loop` 반복 빈도 감소,
  루프 티 완화.
- 97 → 145프레임은 latent 약 +50% — full 모드(20-step)에서 생성 시간 증가
  리스크가 있으나 `VIDEO_GEN_TIMEOUT=1200s` 내 수용 판단. OOM 시 기존 4단계
  폴백(3차부터 768×512 + `min(target, 3.0)`초 = ≤73프레임)이 그대로 안전망.
- oversized 씬은 클립(≤6.04초) < TTS 길이 미스매치가 남지만 이는 기존에도
  존재(렌더러 `loop_or_trim_clip` 처리) — 동작 변화 없음, 상한만 명확해짐.

## 금지사항

- `validate_frame_count()`에 상한을 추가하지 말 것 — 격자 보정과 길이 정책의
  책임 분리를 유지한다.
- `VIDEO_NUM_FRAMES_MAX`를 145 초과로 올리려면 RTX 3090 lowvram에서
  1280×720 기준 OOM 재검증 후 본 ADR을 갱신할 것.
- 씬 병합 범위(min/max)를 코드 기본값만 바꾸지 말 것 —
  `worker/ai_worker/scene/settings.yaml`이 실효 지점이며 `get_domain_setting`은
  lru_cache라 변경 후 worker 재시작이 필요하다.
