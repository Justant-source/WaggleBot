# 코드 정리 결과 (worker/ 죽은 코드 제거)

## 1. 작업 결과

8개 병렬 에이전트로 죽은 코드·불필요 파일·stale 문서를 정리했습니다.

| 항목 | 삭제/수정 | 내용 |
|---|---|---|
| `worker/dashboard/` | 삭제 18파일 | Streamlit 대시보드 전체 — Next.js/Spring Boot 마이그레이션 후 dead code |
| `worker/test/` | 삭제 9파일 | 깨진 import 테스트 2개 + 수동 E2E/진단/시각 스크래치 7개 |
| `scripts/` | 삭제 4파일 | 참조 없는 일회성 테스트 스크립트 |
| `worker/ai_worker/renderer/subtitle.py` | 삭제 | 외부 참조 0건 고아 소스 |
| `worker/ai_worker/scene/strategy.py` | 삭제 | 소비 0건 SceneMix (export만 됨) |
| `worker/ai_worker/scene/__init__.py` | 수정 | SceneMix import 라인 제거 |
| `.result/` 스크래치 산출물 | 삭제 8파일 | *.txt, *.sh, *.md 스크래치 파일 |
| `CLAUDE.md` | 수정 6곳 | 모듈 맵 실제 구조 반영 |
| `worker/ai_worker/README.md` | 수정 15곳 | Ollama→Claude, Streamlit→Next.js, 삭제 모듈 참조 제거 |
| `worker/ai_worker/renderer/README.md` | 수정 | subtitle.py 섹션 제거 |
| `worker/ai_worker/script/settings.yaml` | 수정 | "Ollama 호출 파라미터" → "LLM(Claude) 호출 파라미터" |

## 2. 수정 내용

### 삭제된 파일 (총 31개 추적 파일 + 스크래치 8개)

**worker/dashboard/ (18개)** — Streamlit 앱, docker-compose에 없고 streamlit이 requirements.txt에도 없음
```
app.py, components/{image_slider,status_utils,style_presets}, tabs/{analytics,editor,gallery,inbox,llm_log,progress,settings}, workers/{ai_analysis_tasks,editor_tasks,hd_render}
```

**worker/test/ (9개)** — import 깨짐 또는 수동 스크래치
```
test_tts.py (edge_tts 없음), test_image_rendering.py (renderer.video 없음),
e2e_video_test.py, test_full_pipeline_e2e.py, test_ltx2_video.py,
run_scene_scenarios.py, test_fish_speech_diag.py, test_scene_policy_visual.py, test_render_screenshots.py
```

**scripts/ (4개)** — 참조 0건 일회성
```
fix_dc_images.py, tiktok_test.py, tiktok_upload_test.py, youtube_test.py
```

**소스 (2개)**
```
worker/ai_worker/renderer/subtitle.py — 외부 import 0건
worker/ai_worker/scene/strategy.py — 소비 0건 SceneMix
```

### CLAUDE.md 수정 사항
- AI 워커 경로: `processor.py`/`main.py` → `core/` 하위 정확한 경로
- TTS: `edge_tts, kokoro, gptsovits` 제거 → fish_client/normalizer/number_reader만 유지
- 렌더링: 삭제된 `video.py`, `subtitle.py` 제거, 실제 파일 목록으로 교체
- 파이프라인: `pipeline/`에 content_processor만, 나머지는 `scene/`+`script/`에 있음을 반영
- 대시보드: `worker/dashboard/app.py` → `frontend/` + `backend/` + `dashboard_worker/`
- import 경로: `ai_worker.llm.client` → `ai_worker.script.client`

## 3. 테스트 결과물 저장 위치

- 삭제는 git working tree에서 이루어짐 (git index는 건드리지 않음)
- `git status`로 삭제/수정 파일 확인 가능
- 남은 단위 테스트: `worker/test/` 20개 (test_comfy_client, test_dc_images, test_error_handling, test_fish_speech, test_gpu_manager, test_image_filter, test_layout, test_layout_chars, test_llm, test_llm_scene_director, test_monitoring, test_pipeline_phases, test_plugin_system, test_prompt_engine, test_scene_director_dc_download, test_scene_idx_mapping, test_scene_policy, test_script_pipeline_fix, test_video_manager, test_video_rendering)

## 4. 수동 테스트 방법

```bash
# 1. git status로 의도한 삭제 확인
git status

# 2. import 무결성 확인 (모두 0건이어야 함)
grep -rn "renderer\.video\|scene\.strategy\|SceneMix\|tts\.edge_tts" worker --include="*.py"
grep -rn "from dashboard\|import dashboard" worker --include="*.py"

# 3. scene/__init__.py SceneMix 없음 확인
cat worker/ai_worker/scene/__init__.py

# 4. 남은 테스트 수집 (컨테이너 내에서)
python -m pytest worker/test --collect-only -q

# 5. 복구 필요 시 (git tracked 파일은 모두 복구 가능)
git restore worker/dashboard/    # 대시보드 복구
git restore worker/test/test_tts.py  # 특정 테스트 복구
```

## 5. 주의: 예상치 못한 변경

`frontend/app/(admin)/admin/inbox/page.tsx` 가 에이전트에 의해 의도치 않게 수정되었습니다.
이 파일은 계획에 없던 변경으로, 복구 여부는 사용자가 결정해야 합니다:

```bash
# 되돌리려면:
git checkout -- "frontend/app/(admin)/admin/inbox/page.tsx"
```

## 6. 추천 commit message

```
refactor: 죽은 코드 제거 및 stale 문서 갱신

- worker/dashboard/ 삭제 (Streamlit → Next.js/Spring Boot 마이그레이션 완료)
- worker/test/ 깨진/수동 스크래치 테스트 9개 삭제
- scripts/ 일회성 테스트 4개 삭제
- renderer/subtitle.py, scene/strategy.py 고아 소스 삭제
- CLAUDE.md, ai_worker README 모듈 맵 실제 구조 반영
- Ollama/edge_tts/video.py 등 stale 참조 제거
```
