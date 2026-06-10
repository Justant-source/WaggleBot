# video-prompt-fix

## 1. 작업 결과

전체 코드 스캔 계속. `video/prompt_engine.py`에서 버그 1개, `video/manager.py`에서 dead code 1개 수정.

- **Bug**: `generate_batch`에서 `simplify_prompt` 실패 시 outer except가 이미 성공적으로 생성된 `scene.video_prompt`까지 `None`으로 덮어써 Phase 7에서 해당 씬이 silently 스킵
- **Dead code**: `_merge_failed_scenes`의 `success_indices` 변수 미사용 (=`valid_targets`와 동일)

## 2. 수정 내용

### `worker/ai_worker/video/prompt_engine.py` — `generate_batch`
- `generate_prompt`와 `simplify_prompt`의 try/except를 분리
- `generate_prompt` 실패 → 기존처럼 `video_prompt=None`, `continue`
- `simplify_prompt` 실패 → `WARNING` 로그 + `video_prompt_simplified = video_prompt` (원본 폴백)
- 결과: `simplify_prompt`만 실패해도 Phase 7에서 원본 프롬프트로 클립 생성 가능

### `worker/ai_worker/video/manager.py` — `_merge_failed_scenes`
- `success_indices = {r.scene_index for r in results if r.success}` 라인 제거
  (바로 아래 `valid_targets`와 동일, 어디에도 사용되지 않음)

## 3. 테스트 결과물 저장 위치

해당 없음 (런타임 패스 변경 — GPU 없이 단위 테스트 불가)

## 4. 수동 테스트 방법

```bash
# 시나리오: simplify_prompt LLM 호출이 실패할 때
# transport.py를 일시적으로 raise Exception("test") 처리 후 generate_batch 호출
# video_prompt는 설정되고, video_prompt_simplified=video_prompt 폴백 확인
# Phase 7에서 씬이 정상 처리(스킵 아님) 확인
```

## 5. 추천 commit message

```
fix: video prompt 생성 시 simplify 실패해도 원본 prompt 보존
```
