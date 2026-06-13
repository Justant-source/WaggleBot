# approve-fail 근본 원인 + 수정 결과

## ★ 최종 진짜 원인 — 백엔드 CORS 403 (확정)

진단 토스트로 드러난 실제 에러는 **HTTP 403 "Invalid CORS request"**.
- 브라우저는 상태변경 POST에 `Origin: http://100.115.252.61:3000`를 붙이고, **Next.js 프록시가 이 Origin을 백엔드로 그대로 전달**한다(→ 프록시 경유라도 CORS 검사 대상. 이전 세션의 "프록시라 CORS 무관" 가정이 오류였음).
- 백엔드 `CorsConfig`는 `setAllowedOrigins([frontend-url, localhost:3000])`만 허용 → 사용자의 Tailscale IP Origin이 미허용 → Spring CORS 필터가 **403**.
- 검증: Origin 없음 → 200, `Origin: localhost:3000` → 200, `Origin: 100.115.252.61:3000` → **403**.

**수정** — `backend/src/main/java/com/wagglebot/config/CorsConfig.java`:
- `setAllowedOrigins(...)` → **`setAllowedOriginPatterns(...)`** (credentials와 호환되며 와일드카드 가능)
- 허용 목록을 `app.cors-allowed-origins`(CSV, 기본 `*`) 프로퍼티로 외부화 → 내부망/Tailscale 임의 IP 접속 허용, 필요시 env로 제한.
- `PATCH` 메서드 추가.
- 검증(재빌드 후): 프리플라이트 OPTIONS 200 + POST approve 200(이전 403), 임의 LAN Origin도 200.

> 디버깅 흐름: 정적캐시 수정 → 사용자가 새 번들+진단토스트 수신 → 토스트가 진짜 403 노출 → CORS 수정. 셋 다 필요한 연쇄였다.

---


## 0. 사용자 증상의 진짜 원인 — 관리자 페이지 1년 정적 캐시 (핵심)

"수신함 승인 직후 빨간 '승인 실패' 토스트"의 직접 원인은 **Next.js가 관리자 페이지를 1년 정적 캐시**해서 사용자 브라우저가 옛 번들을 계속 실행한 것:
- `/admin/*` 응답 헤더가 `Cache-Control: s-maxage=31536000, stale-while-revalidate` + `x-nextjs-cache: HIT`
- 프론트를 재빌드해도(서버는 최신 코드 서빙 확인 — 청크에 신규 진단 코드 포함됨) **브라우저가 1년치 캐시된 옛 HTML/청크를 로드** → 고쳐지기 전 approve 코드 실행 → 백엔드 200에도 화면은 '승인 실패'
- 근거: 해당 포스트(`엄마가 수술중`, id 10000176) 승인 API도 프록시 경로에서 **HTTP 200**(jobId 44). 서버·백엔드는 정상, 순수 브라우저 캐시 문제.

**근본 수정:**
- `frontend/app/(admin)/layout.tsx`에 **`export const dynamic = 'force-dynamic'`** 추가 → 모든 관리자 라우트가 `Cache-Control: private, no-cache, no-store, must-revalidate`로 서빙(검증 완료). 정적 캐시 영구 차단.
- `frontend/.../inbox/page.tsx`: 승인/거절 실패 토스트에 **실제 에러 표시**(`apiErr()`) 추가 → DevTools 없이 원인(HTTP 코드/네트워크) 진단 가능.
- `docker compose up -d --build frontend` 재빌드.

**사용자 1회 조치:** 브라우저가 이미 1년치 옛 페이지를 캐시했으므로 **시크릿 창으로 접속**하거나 **강력 새로고침(Ctrl+Shift+R)** 1회 필요. 이후엔 no-store라 항상 최신.

> 교훈: frontend는 prod 빌드(`next-server`)이고, 관리자 라우트는 기본적으로 정적 캐시된다. 소스 수정 후 `up -d --build frontend` 재빌드 + 관리자 라우트는 `force-dynamic` 필수.

---

## 1. 작업 결과 (ai_worker 파이프라인 — 별개 버그)

inbox 승인 → 확정 후 ai_worker 파이프라인이 **민감하지 않은 게시글에도 간헐적으로 FAILED** 되는 현상의 근본 원인을 찾아 수정하고, 회귀 테스트(14개) + 라이브 풀 파이프라인 e2e로 검증했다.

### 근본 원인 (2가지)

**① LLM JSON 파서 취약성 (핵심)**
- LLM 프록시(`api.clcocloud.com`)의 haiku/sonnet이 `json_mode` 지시("No code fences")를 무시하고 ` ```json ... ``` ` 펜스나 설명 prose를 자주 덧붙인다.
- 기존 `call_llm_json`은 `json.loads(raw)` 실패 시 **탐욕적 정규식** `r"\{.*\}"` 하나로만 폴백했다. 이 정규식은:
  - JSON 뒤에 예시용 두 번째 `{...}`가 붙으면 둘 다 삼켜 invalid → `{}`
  - JSON 앞뒤 prose에 리터럴 중괄호가 있으면 깨짐 → `{}`
  - 응답이 잘리면(truncation) → `{}`
- `{}`가 되면 `chunk_with_llm`이 `ValueError: 필수 키 누락 'hook'` → 포스트 **FAILED**.
- benign 콘텐츠도 LLM 출력 형태에 따라 **간헐적으로** 이 경로를 타서 "아무 이유 없이 실패"로 보였다.

**② 콘텐츠 거부를 기술적 실패와 혼동**
- LLM이 정치/민감 콘텐츠를 거부하면 prose만 반환 → `{}` → 동일한 `ValueError` → FAILED(재시도 대상). 거부는 재시도해도 실패하므로 DECLINED가 맞다.

## 2. 수정 내용

### `worker/ai_worker/llm/transport.py`
- `LLMContentRefusalError` 예외 클래스 추가.
- **`extract_json_object(raw)` 신규** — 견고한 다단계 JSON 추출:
  1. 그대로 `json.loads`
  2. ` ```json ... ``` ` 코드펜스 제거 후 재시도
  3. **모든 `{` 위치에서 `raw_decode`** — 한 객체만 파싱해 트레일링 펜스/prose 무시, 앞쪽 prose의 중괄호도 건너뜀, 내용 있는 첫 dict 우선
  4. 탐욕적 정규식(최후의 수단)
- `call_llm_json`이 이 추출기를 사용하도록 변경.

### `worker/ai_worker/script/chunker.py`
- LLM 응답이 빈 dict면 `ValueError` 대신 `LLMContentRefusalError` 발생.

### `worker/ai_worker/core/main.py`
- `_mark_post_declined()` 추가.
- `_llm_tts_worker`에서 `LLMContentRefusalError` → DECLINED(재시도 안 함), 그 외 → 기존대로 FAILED.

### `worker/ai_worker/scene/director.py`
- 자체 `_extract_json_from_response`의 중복 fragile 정규식을 공용 `extract_json_object`로 통일.
- scene_director LLM `max_tokens` 2048 → **4096** (씬 20+ 게시글에서 JSON 잘려 rule_based 폴백으로 떨어지던 품질 저하 방지).

## 3. 테스트 결과물 위치

- **회귀 테스트:** `worker/test/test_llm_json_robust.py` — **14/14 PASS**
  - `extract_json_object` 11종(펜스/prose/중첩/거부/두 번째 객체/앞쪽 중괄호 prose 등)
  - `call_llm_json` 펜스 처리·거부 시 빈 dict
  - `chunk_with_llm` 거부 → `LLMContentRefusalError`, 정상 → 대본 dict
- **구 파서 회귀 증명:** `second_object`/`prose_with_braces` 케이스에서 OLD=깨짐, NEW=정상 확인.
- **라이브 풀 파이프라인 e2e:** post 10000156(비민감 "손흥민 활용방안")을 APPROVED→ 전체 파이프라인 통과 확인 — chunk✓ TTS✓ scene_director✓ video_prompt 7개✓ ComfyUI 클립 생성✓ (→ PREVIEW_RENDERED).

## 4. 수동 테스트 방법

```bash
# 1) 회귀 테스트 (pytest 불필요, 내장 러너)
docker exec env-ai_worker-1 bash -c "cd /app && python test/test_llm_json_robust.py"

# 2) 라이브 e2e: 비민감 COLLECTED 포스트를 승인 흐름에 투입
docker exec env-db-1 mariadb -uroot -pwagglebot_root wagglebot \
  -e "UPDATE posts SET status='APPROVED', last_error=NULL WHERE id=<benign_id>;"
docker compose -f env/docker-compose.yml logs -f ai_worker   # Pipeline 단계별 로그 관찰
#   기대: chunk→TTS→scene→prompt→video clip→render → status=PREVIEW_RENDERED (FAILED 아님)

# 3) 거부 콘텐츠는 DECLINED로 떨어지는지(정치 게시글)
#   기대 로그: "LLM 콘텐츠 거부" + "콘텐츠 거부로 DECLINED 처리"
```

## 5. 추천 commit message

```
fix: LLM JSON 파싱 견고화 — 펜스/prose로 인한 간헐적 FAILED 제거

프록시 LLM이 json_mode를 무시하고 ```json 펜스·설명 prose를 붙여
탐욕 정규식 폴백이 {}를 반환 → chunk가 'hook' 누락 ValueError로
포스트를 FAILED 시키던 문제. extract_json_object(코드펜스 제거 +
모든 '{'에서 raw_decode)로 통일하고 scene_director 파서도 일원화.
콘텐츠 거부는 LLMContentRefusalError→DECLINED로 분기(재시도 차단).
scene_director max_tokens 2048→4096(씬 다수 잘림 방지).

회귀 테스트 worker/test/test_llm_json_robust.py 14종 추가.
```

## 6. DOC-MAP 기준 갱신한 문서 목록

없음 — 코드 내 오류 처리·파싱 로직 수정에 한정(아키텍처·API·설정·DB 스키마 변경 없음). `docs/implementation-status.md`에 버그 픽스 이력 1줄 추가는 선택.
