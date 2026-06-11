# 대본 리텐션 프롬프트 개편 + 활성 경로 입력 격차 수정

커뮤니티 인기글 → 쇼츠 대본 생성용 Sonnet 프롬프트를 "시청자가 끝까지 보게 만드는" 리텐션 중심으로 개편하고,
자동 파이프라인의 활성 경로(`chunk_with_llm`)가 제목·베스트 댓글·성과 피드백을 LLM에 전달하지 못하던 결함을 수정했다.
자극은 내용(반전·궁금증·감정 낙차)으로 극대화하고 표현 순화(광고 친화) 원칙은 유지했다.

## 1. 작업 결과

- **프롬프트 §2 리텐션 설계 전면 개편** (chunker.py·client.py 동기화):
  - 2-1 Hook 강화: 기존 4공식 + 1인칭 고백·후회형(⑤) 추가, 구체 명사/숫자 1개 이상 의무, 첫 어절 강조
  - 2-2 Hook-Payoff 계약: hook의 답은 body 마지막 1/3에서만 해소 (초반 노출 금지, 단 낚시 금지)
  - 2-3 에스컬레이션 체인: "그리고" 나열 금지 → "근데/알고 보니" 전환·고조
  - 2-4 블록 클리프행어 / 2-5 감정 낙차 / 2-6 중간 떡밥(mood별) / 2-7 Closer 업그레이드(편가르기·루프형, 20자 명시)
  - 출력 전 자가점검 3항 추가, few-shot 예시를 리텐션 곡선 시범으로 교체
- **입력 격차 수정 (활성 경로 결함)**: `chunk_with_llm()`이 본문 2000자만 받던 것을 제목 + 본문 4000자 + 베스트 댓글 5개 + 성과/A·B 피드백까지 받도록 확장 → `type=comment` 인용 씬과 피드백 루프가 활성 경로에서 부활.
- **공통화**: 레거시 경로(processor.py)에만 있던 피드백+A/B 조립 로직을 `analytics.feedback.build_extra_instructions()`로 추출, 활성·레거시·content_processor 3경로 공유.
- **출력 스키마/파서 계약 100% 보존** — hook/body/closer/title_suggestion/tags/mood, type=comment·author 분리, lines≤20자, mood 9종 불변. 다운스트림(validate_and_fix·parser·SceneDirector) 무영향.

## 2. 수정 내용

| 파일 | 변경 |
|------|------|
| `worker/ai_worker/llm/transport.py` | `call_llm_json()`에 `temperature: float = 0.5` 파라미터 추가 → `call_llm`으로 전달 (기본값 동일, 기존 호출처 무영향) |
| `worker/analytics/feedback.py` | `build_extra_instructions(post_id=None, session=None)` 신설 — feedback_config의 extra_instructions + mood_weights>1.1 선호 힌트 + Content.variant_config(A/B) 조립. 모든 실패 흡수(None 반환) |
| `worker/ai_worker/script/chunker.py` | `_build_chunking_user`/`create_chunking_prompt`/`chunk_with_llm` 시그니처에 `title`·`best_comments`·`extra_instructions` keyword 인자 추가(하위호환). user tail에 제목·베스트 댓글·추가 지시 섹션 구성. 본문 절단 2000→4000자. `build_chunking_system()` §2 리텐션 7기법 전면 개편 + 페르소나 목표 함수 1줄 + 자가점검 + few-shot 교체. `_call_llm_json_sync` temperature=0.7 |
| `worker/ai_worker/core/processor.py` | `_safe_generate_summary`의 인라인 피드백+A/B 로직을 `build_extra_instructions()` 호출로 교체. `llm_tts_stage` use_cp 분기에 title·best_comments·extra_instructions 전달 |
| `worker/ai_worker/pipeline/content_processor.py` | Phase 2 호출에 title·best_comments·extra_instructions 전달 (세션 미보유 → helper 내부 SessionLocal, 댓글 접근 방어적 try) |
| `worker/ai_worker/script/client.py` | `_SCRIPT_SYSTEM` "핵심 원칙 3"을 3-1~3-7 리텐션 기법으로 확장, 예시 closer 24→14자(20자 준수), body 항목 수 23→30 통일, max_tokens 2048→8192, title_suggestion 불일치 주석 기록 |
| `docs/pipeline.md` | Phase 2 입력 구성·temperature 명시, **Phase 3 설명 정정**(LLM 재분할 → 로컬 smart_split 보정), 피드백 루프 다이어그램 갱신 |
| `docs/implementation-status.md` | 변경 이력 추가 |
| `worker/test/test_chunker_retention.py` | 신규 — 입력 격차·리텐션 섹션·예시 JSON·하위호환·temperature 검증 6개 |

## 3. 테스트 결과물 위치

- 신규 테스트: `worker/test/test_chunker_retention.py` (6 passed)
- 기존 회귀: `worker/test/test_script_pipeline_fix.py` + `test_e2e_structure_improve.py` (32 passed, 2 skipped)
- 실게시글 E2E LLM 로그: `llm_logs` 테이블 `call_type='chunk'` 최신 행(id=188, post_id=71) — prompt_text에 제목·베스트 댓글·추가 지시 섹션 포함, raw_response 스키마/길이 제약 충족
  - 출력 검수 결과: hook 19자(≤40), closer 15자(≤20, 편가르기형 "이 남편, 이혼해줘야 해요?"), body 27항목 중 comment 3개(댓글 인용 부활), body 줄 길이 위반 0건, payoff가 마지막 1/3([17-22])에 배치됨

## 4. 수동 테스트 방법

> Python 의존성은 Docker 컨테이너에만 설치됨. 아래는 컨테이너 기준.

1. **단위 테스트**:
   ```
   docker compose -f env/docker-compose.yml exec ai_worker python -m pytest test/test_chunker_retention.py test/test_script_pipeline_fix.py -q
   ```
2. **실게시글 Phase 2 단독 호출** (리텐션 구조·댓글·길이 육안 검수):
   ```
   docker compose -f env/docker-compose.yml exec ai_worker python -c "
   import asyncio; from db.session import SessionLocal; from db.models import Post
   from ai_worker.scene.analyzer import analyze_resources
   from ai_worker.script.chunker import chunk_with_llm
   ... (post 로드 → title/best_comments 추출 → chunk_with_llm 호출 → 출력 검수)"
   ```
   (본 작업에서 post_id=71로 실행, 정상 확인)
3. **LLMLog 검수**: `SELECT prompt_text, raw_response FROM llm_logs WHERE call_type='chunk' ORDER BY id DESC LIMIT 1;` — 제목/베스트 댓글/추가 지시 섹션 포함 확인
4. **캐시 적중**(backend=api): 게시글 2건 연속 처리 후 `docker compose logs ai_worker | grep "cache_read"` → 2건째 cache_read>0 (system prefix 정적성 확인)
5. **대시보드 재생성 경로**: 편집실 대본 재생성 1건 → generate_script(client.py) 새 리텐션 구조 반영 확인

## 5. 추천 commit message

```
feat: 대본 Sonnet 프롬프트 리텐션 개편 + 활성 경로 입력 격차 수정

- chunker.py·client.py §2 리텐션 설계 전면 개편: Hook-Payoff 계약,
  에스컬레이션 체인, 클리프행어, 감정 낙차, 편가르기 Closer, 자가점검
- chunk_with_llm에 제목·베스트 댓글·성과 피드백 전달 → type=comment
  인용 씬·피드백 루프 부활, 본문 절단 2000→4000자, temperature 0.7
- analytics.feedback.build_extra_instructions() 공통 helper 추출
- call_llm_json temperature 파라미터, client max_tokens 8192
- docs/pipeline.md Phase 2/3 정정, test_chunker_retention.py 추가

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
```

## 6. DOC-MAP 기준 갱신한 문서 목록

- `docs/pipeline.md` — Phase 2 입력 구성·temperature, Phase 3 로컬 보정 정정, 피드백 루프 다이어그램
- `docs/implementation-status.md` — 변경 이력 추가
- (ADR 불필요: 하드 제약·스키마 불변 / docs/config.md 불필요: settings 변수 무변경)
