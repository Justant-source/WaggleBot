# python-models

## 1. 작업 결과

Python 워커 핵심 모듈 4개 수정/생성 완료: DB 모델 컬럼 추가, 핸들러 3곳 개선, progress 헬퍼 신규, AB 프리셋 config 로드.

| 항목 | 파일 | 내용 |
|------|------|------|
| Post AI 분석 컬럼 추가 | `worker/db/models.py` | ai_score, ai_reason, ai_recommended, ai_analyzed_at 4개 컬럼 |
| Content 신규 컬럼 추가 | `worker/db/models.py` | tts_voice, gen_instructions 2개 컬럼 |
| _handle_ai_fitness 재작성 | `worker/dashboard_worker/handlers.py` | raw 반환 → JSON 파싱 + Post 영속화 |
| _handle_generate_script 수정 | `worker/dashboard_worker/handlers.py` | gen_instructions DB 저장 추가 |
| _handle_tts_preview 수정 | `worker/dashboard_worker/handlers.py` | content.tts_voice 폴백 추가, 중복 DB 조회 제거 |
| progress.py 신규 생성 | `worker/ai_worker/core/progress.py` | stamp_progress / clear_checkpoint_keep_progress 헬퍼 |
| VARIANT_PRESETS config 로드 | `worker/analytics/ab_test.py` | _load_variant_presets() 함수로 config/prompt_presets.json 우선 로드 |

## 2. 수정 상세

### models.py — Post 컬럼 4개
- `ai_score`: Integer nullable — AI 분석 점수 0~100
- `ai_reason`: String(500) nullable — 분석 이유 한국어
- `ai_recommended`: Boolean nullable — 추천 여부
- `ai_analyzed_at`: DateTime(timezone=True) nullable — 분석 시각

### models.py — Content 컬럼 2개
- `tts_voice`: String(32) nullable — 게시글별 TTS 보이스 키
- `gen_instructions`: String(1000) nullable — 대본 생성 시 사용된 지시문

### handlers.py — _handle_ai_fitness
- 기존: `call_llm_raw()` 결과를 `{"raw": raw}` raw 텍스트로만 반환
- 변경: `re.search(r'\{[^}]+\}')` 로 JSON 블록 파싱 → score/reason/recommended 추출 → Post에 영속화
- 파싱 실패 시 ValueError 발생 (Job.error에 기록됨)
- `call_type="ai_fitness"` 전달로 haiku 모델 라우팅

### handlers.py — _handle_generate_script
- `content.summary_text = script.to_json()` 직후 `if extra_instructions: content.gen_instructions = extra_instructions[:1000]` 추가
- variant_config 코드 미변경

### handlers.py — _handle_tts_preview
- `voice_key = payload.get("voice", cfg.get(...))` → `voice_key = payload.get("voice") or _post_voice or cfg.get(...)`
- content 조회 1회로 통합 (기존 두 번 → 한 번)
- `_post_voice = content.tts_voice` SessionLocal 블록 안에서 읽어 블록 밖에서 사용

### progress.py (신규)
- `stamp_progress(post_id, phase, phase_name, ...)` — pipeline_state['progress'] 머지 업데이트
- 동일 phase 재호출 시 phase_started_at 유지 (시작 시각 보존)
- `clear_checkpoint_keep_progress(post_id)` — phase/video_scenes_done/video_clips/total_scenes 키 제거, progress 보존
- 모든 DB 오류는 logger.warning으로 비치명 처리

### ab_test.py — _load_variant_presets()
- `config/prompt_presets.json` 존재 시 `{p["key"]: {"extra_instructions": ...}}` 형태로 로드
- 없거나 파싱 실패 시 기존 하드코딩 6종(hook_question/hook_exclamation/body_short/body_narrative/tone_formal/tone_casual) 폴백

## 3. 테스트 결과물 위치

해당 없음 (DB 마이그레이션은 Step 0에서 별도 적용 필요).

## 4. 수동 테스트 방법

```
1. AI 적합도 분석:
   대시보드에서 게시글 선택 → AI 적합도 분석 실행
   → jobs 테이블 result 확인: {"score": N, "reason": "...", "recommended": true/false}
   → posts 테이블: ai_score, ai_reason, ai_recommended, ai_analyzed_at 컬럼 업데이트 확인

2. 대본 생성 + gen_instructions:
   편집실에서 지시문 입력 후 대본 재생성
   → contents 테이블: gen_instructions 컬럼 저장 확인

3. TTS 프리뷰 보이스 폴백:
   특정 포스트 contents.tts_voice = 'other_voice' 수동 설정
   → payload에 voice 없는 TTS 프리뷰 실행
   → content.tts_voice 값으로 합성 확인

4. progress 헬퍼:
   from ai_worker.core.progress import stamp_progress
   stamp_progress(1, 3, "validate_and_fix")
   → contents 테이블 pipeline_state['progress'] 확인

5. A/B 프리셋 config 로드:
   config/prompt_presets.json 생성 후 ai_worker 재시작
   → ab_test.VARIANT_PRESETS가 파일 내용으로 로드됨 확인
```

## 5. 추천 commit message

```
feat: Post AI 분석 컬럼 + Content 보이스/지시문 컬럼 + 핸들러 개선 + progress 헬퍼 신규
```
