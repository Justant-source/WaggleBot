# Marketing quality gates

## 작업 결과
Again-Spring pre-scripted Reels/Shorts가 길이와 실제 시봄이 삽입을 검증한 뒤에만 PREVIEW_RENDERED로 진행한다.

## 수정 내용
- Reels 30/32초, Shorts 45/47초 TTS/MP4 gate
- 최초 TTS 초과 시 hook/CTA 보존 문장 경계 축약 후 한 번만 재합성
- 시봄이 씬 문장 분할, 중복 없는 beat 재배치, 실적 최소 4/5장 gate
- `pipeline_state.generation_diagnostics`와 external GET 응답의 `generationDiagnostics`

## 테스트 결과물 위치
- `worker/test/test_sibom_plan_director.py` PASS
- Python quality helper smoke PASS
- `backend` Gradle compile/test PASS (test source 없음)

## 수동 테스트 방법
Again-Spring external pre_scripted job에 `platformLayout=reels_compact` 또는 `shorts_standard`와 sibomPlan을 보내고 GET 상태의 `generationDiagnostics` 및 FAILED failure_code를 확인한다.

## 추천 commit message
`fix(marketing): gate waggle renders by duration and sibom coverage`

## Doc-Sync
필요: docs/30-components/pipeline.md 및 docs/50-api/rest-spec.md를 상위 통합 커밋에서 갱신.
