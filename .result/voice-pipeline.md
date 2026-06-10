# voice-pipeline

## 1. 작업 결과

Python 파이프라인 보이스 관통 + 진행 스탬프 삽입 완료. 4개 파일 수정.

| 파일 | 수정 내용 |
|------|------|
| `worker/ai_worker/core/processor.py` | `_resolve_post_voice` 헬퍼 추가, `_safe_generate_tts` voice_override 파라미터화, `llm_tts_stage` stamp + 보이스 전달, `render_stage` stamp + 보이스 전달, `_on_scene_complete` 머지형 체크포인트, 체크포인트 클리어 교체 |
| `worker/ai_worker/renderer/layout.py` | `render_layout_video_from_scenes` + `render_layout_video` 모두 `voice_key: str | None = None` 파라미터 추가, voice 결정 로직 `voice_key or ...` 방식으로 변경 |
| `worker/ai_worker/renderer/composer.py` | `render_final_video` `voice_key: str | None = None` 파라미터 추가, `render_layout_video` 호출에 `voice_key=voice_key` 전달 |
| `config/settings.py` | `VOICE_PRESETS` 하드코딩 딕셔너리 → `_load_voice_presets()` 함수(voices.json 우선 로드, 없으면 폴백)로 교체 |

## 2. 수정 상세

### processor.py — `_resolve_post_voice` (모듈 레벨 헬퍼)
- `Content.tts_voice` 조회, 없으면 `None` 반환 → 전역 pipeline.json `tts_voice` 폴백

### processor.py — `_safe_generate_tts`
- 시그니처: `voice_override: str | None = None` 파라미터 추가
- `voice_id = voice_override or self.cfg.get("tts_voice", "default")`

### processor.py — `llm_tts_stage` 스탬프 + 보이스
- `post.status = PostStatus.PROCESSING` 직후: `stamp_progress(post_id, 1, "자원 분석")`
- `chunk_with_llm` / `_safe_generate_summary` 직전: `stamp_progress(post_id, 2, "대본 생성")`
- `_safe_generate_tts` 직전: `_post_voice = _resolve_post_voice(post_id)` + `stamp_progress(post_id, 5, "TTS 합성")`
- TTS 완료 후: `stamp_progress(post_id, 5, "TTS 합성", done=True)`

### processor.py — `render_stage` 스탬프 + 보이스
- `SceneDirector` 직전: `stamp_progress(post_id, 4, "씬 구성")`
- FFmpeg 렌더링 직전: `stamp_progress(post_id, 8, "FFmpeg 렌더링")` + `_post_voice = _resolve_post_voice(post_id)`
- `render_layout_video_from_scenes` 호출에 `voice_key=_post_voice` 전달

### processor.py — `_generate_video_clips` Phase 6/7 스탬프
- Phase 6 VideoPromptEngine 생성 직전: `stamp_progress(post_id, 6, "비디오 프롬프트")`
- `generate_all_clips` 직전: `stamp_progress(post_id, 7, "비디오 클립", scenes_done=0, total_scenes=len(scenes))`

### processor.py — `_on_scene_complete` 머지형 쓰기
- 기존: `ct.pipeline_state = VideoCheckpoint(...).to_dict()` (progress 덮어씀)
- 변경: 기존 `pipeline_state` 읽기 → `state.update(checkpoint_dict)` → `state["progress"]` 갱신 → 단일 쓰기
- `phase_started_at`: phase 7이 이미 진행 중이면 기존 시작 시각 보존

### processor.py — Phase 7 클리어
- 기존: `with SessionLocal()` 블록으로 `ct.pipeline_state = None`
- 변경: `clear_checkpoint_keep_progress(post_id)` (progress 보존, 체크포인트 키만 클리어)

### layout.py — 두 public 함수 voice_key 파라미터화
- `render_layout_video(post, script, output_path=None, voice_key=None)`
- `render_layout_video_from_scenes(post, scenes, ..., voice_key=None)`
- 씬별 `voice_override`(_tts.py 처리)는 무변경

### composer.py — `render_final_video` voice_key 관통
- `voice_key: Optional[str] = None` 파라미터 추가
- `render_layout_video(..., voice_key=voice_key)` 전달

### settings.py — `_load_voice_presets()`
- `config/voices.json` 존재 시 `{"voices": [{"key":..., "file":...}, ...]}` 구조에서 로드
- 파일 없거나 파싱 실패 시 기존 8개 하드코딩 폴백

## 3. 의존 모듈 주의사항
- `worker/ai_worker/core/progress.py`는 별도 에이전트가 생성 예정 — `stamp_progress`, `clear_checkpoint_keep_progress` API 맞춰 import 완료
- `Content.tts_voice` 컬럼은 `python-models` 에이전트가 추가 완료

## 4. 수동 테스트 방법
```bash
# TTS 보이스 관통 확인
docker compose logs -f ai_worker | grep -E '\[voice\]|\[Pipeline'

# 진행 스탬프 확인
docker compose logs -f ai_worker | grep -E 'stamp_progress|Phase [1-8]'

# pipeline_state 확인
docker exec wagglebot-db-1 mysql -u wagglebot -pwagglebot wagglebot \
  -e "SELECT id, pipeline_state FROM contents LIMIT 5\G"
```

## 5. 추천 commit message
```
feat: 파이프라인 보이스 관통 + 진행 스탬프 삽입

- processor: _resolve_post_voice 헬퍼, _safe_generate_tts voice_override 파라미터화
- llm_tts_stage / render_stage: Phase 1/2/4/5/6/7/8 stamp_progress 삽입
- _on_scene_complete: 체크포인트+progress 머지형 단일 쓰기
- Phase 7 클리어: clear_checkpoint_keep_progress 교체 (progress 보존)
- layout/composer: voice_key 파라미터 관통
- settings: VOICE_PRESETS → _load_voice_presets() (voices.json 우선 로드)
```
