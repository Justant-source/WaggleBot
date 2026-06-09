# 프롬프트 강화 + Claude API 캐싱

qwen2.5 시절에 맞춰져 있던 LLM 프롬프트 2종(① 커뮤니티 사연→유튜브 쇼츠 대본, ② LTX-2 비디오)을
현재 백엔드인 Claude(haiku/sonnet)에 맞게 전면 강화하고, Anthropic API 프롬프트 캐싱을 도입했다.

## 1. 작업 결과

- **대본 프롬프트**(chunker.py·client.py): "AI가 쓴 티" 제거 + 유튜브식 자극(강하되 광고-안전) + 리텐션 설계.
  - 페르소나를 "썰 전문 쇼츠 내레이터"로 선명화, 1인칭 구어체·추임새·문장 리듬 변주 규칙.
  - 자극=균형: 강한 후킹·궁금증 갭은 극대화하되 욕설·혐오·노골 표현은 광고친화적으로 순화(서사 100% 유지, 단어만 순화).
  - 리텐션 3단: Hook(오픈루프/궁금증갭/반전예고/극단수치 4공식, 명사형 요약 금지) → 중간 떡밥("여기서부터가 진짜") → Closer(댓글 참여 유도).
  - few-shot 완성 예시 1개씩 삽입(품질 고정 + 캐시 prefix 토큰 확보).
- **비디오 프롬프트**(prompt_engine.py): LTX-2 6요소(Shot·Scene·Action·Character·Camera·Audio) 구조화 + anti-AI-look 사실성 큐(natural skin texture, candid documentary, motivated 자연광, no oversaturation/CGI) + `video_styles.json` 상세 필드(style_hint·camera_hints·color_palette) 연동. I2V는 identity/외형 드리프트 방지 강화.
- **Claude API 캐싱**: 대본 프롬프트를 "정적 prefix(페르소나·규칙·스키마·예시) + 동적 tail(실제 게시글)"로 분리하고, transport에서 정적 prefix를 `cache_control: ephemeral` 시스템 블록으로 전송. Sonnet(대본)만 적용 — Haiku(비디오)는 최소 캐시 토큰(4096) 미달이라 의도적으로 미적용.
- **출력 스키마/파싱 계약은 100% 보존** — hook/body/closer, comment type/author 분리, lines≤20자, mood 9종 등 기존 계약 불변. 다운스트림(validate_and_fix·parse_script_json·ensure_comments·ComfyUI) 무영향.

## 2. 수정 내용

| 파일 | 변경 |
|------|------|
| `worker/ai_worker/llm/transport.py` | `call_llm`/`call_llm_json`에 `system`·`cache_prefix` 키워드 추가(기본값=하위호환). api 백엔드: 캐싱 활성 시 `system`을 `cache_control` 블록으로(ttl 5m/1h), 아니면 평문. json_mode 지시문은 캐시 블록에 병합. cli 백엔드: `system+prompt` 합본 전송(캐싱 no-op). 응답 `usage`(cache_read/creation/input) debug 로깅(예외 안전). `_get_cache_settings`/`_merge_json_instruction` 헬퍼 추가. |
| `worker/ai_worker/script/chunker.py` | `build_chunking_system(extended)`(정적 prefix)+`_build_chunking_user()`(동적 tail) 분리. `create_chunking_prompt`/`chunk_with_llm` 시그니처·반환·로깅 보존(테스트 호환). `chunk_with_llm`이 `call_llm_json(user, system=…, cache_prefix=True)` 호출. `MAX_HOOK_CHARS` import. |
| `worker/ai_worker/script/client.py` | `_SCRIPT_SYSTEM`(정적, 단일 중괄호 JSON)+`_SCRIPT_USER_TMPL`(동적, `{title}{body}{comments}`) 분리. `_SCRIPT_PROMPT_V2` 합본 별칭 유지(하위호환). `generate_script`가 `call_llm(user, system=_SCRIPT_SYSTEM, cache_prefix=True)` 호출. `extra_instructions`는 동적 user tail에만(캐시 무효화 방지). hook 길이 15자→한 호흡(~12–25자, 최대 MAX_HOOK_CHARS). |
| `worker/ai_worker/video/prompt_engine.py` | T2V 6요소 구조화 + 사실성 큐 + mood 상세 스타일 주입(`{style_detail}{color_palette}{camera_options}{atmosphere}`). `_get_style_block()` 추가(`_get_style_hint` 위임). I2V identity·외형 보존 강화. NEGATIVE_PROMPT에 oversaturated/plastic skin/face morphing 등 추가. **리뷰 반영 수정 6건**: ① person-fallback `in animated style`→photorealistic(no-anime 계약 충돌 제거) ② `max_tok 180→220` + `under 200→150 words`(필수 SOUND 절단 방지) ③ MOOD STYLING을 "subtle photorealistic equivalent"로 종속 ④ I2V strength-guide 줄 제거(생성 파라미터 누출 방지) ⑤ I2V 의상·색·배경·조명 보존 절 추가 ⑥ `body_summary` 미사용 docstring 명시. |
| `config/settings.py` | `_PIPELINE_DEFAULTS`에 `llm_prompt_cache="true"`·`llm_cache_ttl="5m"` 추가. |
| `config/pipeline.json` | 동일 키 추가. |
| `worker/test/test_llm.py` | import를 `_SCRIPT_SYSTEM`/`_SCRIPT_USER_TMPL`로 동기화, 프롬프트 빌드 갱신. |

## 3. 테스트 결과물 저장 위치

- dep-free 정적 검증 통과 로그(이 작업 중 실행): 8개 파일 `ast` 구문 OK / `_SCRIPT_USER_TMPL`·`_T2V_PROMPT_SYSTEM_V2`·`_I2V_SYSTEM` `.format()` placeholder 정합 OK / `pipeline.json`·`video_styles.json` JSON 유효 OK.
- 멀티에이전트 적대적 리뷰 산출물(transcript): `.claude/projects/.../subagents/workflows/wf_09c5ccd4-bb1/agent-*.jsonl` (비디오 렌즈 7건 findings 회수 → 6건 반영).
- 별도 테스트 산출 파일은 없음(아래 수동 테스트로 검증).

## 4. 수동 테스트 방법

> 본 레포의 Python 의존성(sqlalchemy/torch 등)은 **Docker 컨테이너 안에만** 설치돼 있어 호스트에서는 import 실행이 불가. 아래는 컨테이너 기준.

1. **정적 검증(호스트 가능)**: 위 dep-free 스크립트(ast+`.format`+json) 재실행 → `ALL_OK` 확인.
2. **대본 생성(컨테이너)**: `docker compose -f env/docker-compose.yml exec ai_worker python worker/test/test_llm.py` → `worker/test/test_llm_output/*.txt`에서 hook/호흡분할/댓글(author 분리)/closer 품질, lines≤20자 육안 확인.
3. **비디오 프롬프트(컨테이너)**: `docker compose ... exec ai_worker pytest worker/test/test_prompt_engine.py -v` (LLM 호출 필요).
4. **캐시 적중 확인(backend=api)**: 게시글 2건 연속 처리 후 `docker compose logs ai_worker | grep "API usage"` → 1건째 `cache_creation>0`, 2건째 `cache_read>0`. (비디오/Haiku는 0이 정상.)
5. **대시보드 편집실**: 1건 재생성하여 톤·자극 수위·리텐션 장치 육안 점검.

## 5. 추천 commit message

```
feat: qwen→Claude 프롬프트 전면 강화 + API 프롬프트 캐싱

- 대본(chunker/client): 썰 내레이터 페르소나, 자극=균형(광고-안전),
  리텐션 3단(Hook 4공식/중간 떡밥/Closer 참여유도), few-shot 예시 1개씩
- 비디오(prompt_engine): LTX-2 6요소 구조화 + anti-AI-look 사실성 큐,
  video_styles 상세필드(style/camera/palette) 연동, I2V identity 보존 강화
- 캐싱: 정적 prefix/동적 tail 분리, transport에 system+cache_control(ephemeral)
  지원(Sonnet 대본만, Haiku 비디오는 최소토큰 미달로 미적용),
  llm_prompt_cache/llm_cache_ttl 설정 추가
- 출력 스키마/파싱 계약 100% 보존
```
