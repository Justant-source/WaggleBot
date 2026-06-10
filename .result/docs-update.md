# docs-update — README/CLAUDE 갱신 + LLM 정합성 수정

## 1. 작업 결과
qwen2.5/Ollama 잔재를 제거하고 현재 구조(Claude CLI·API 백엔드, Next.js+Spring Boot 대시보드, `env/` compose 단위, 11개 서비스)에 맞춰 문서를 갱신. 추가로 발견된 코드 불일치 2건을 수정.

## 2. 수정 내용

### 문서
- **README.md** (전면 재작성)
  - LLM: Ollama/qwen2.5 → Claude(haiku/sonnet/opus), CLI/API 백엔드 2가지 전환 방식
  - 설치: Ollama 단계 삭제 → Claude CLI 인증 / `ANTHROPIC_API_KEY`
  - 대시보드: Streamlit(8501) → Next.js `/admin`(3000) + Spring Boot(8080), 7개 페이지
  - 실행: `docker compose -f env/docker-compose.yml ...`, `.env`=`env/.env`
  - DB: Flyway 자동 마이그레이션(V1/V2)
  - 서비스 표(11개), 프로젝트 구조 트리, 8-Phase 표 갱신
- **CLAUDE.md** (타깃 수정)
  - 모듈 구조: `worker/llm/` 게이트웨이·`telegram/` 행 추가, frontend 페이지 명시
  - 서비스 표: fish-speech `8082:8080`, llm-worker Spring Boot/opus, `telegram-bridge`, compose 실행 경로
  - 코딩 규칙: import 예시 `call_ollama_raw`→`call_llm`, "Ollama/qwen2.5 미사용" 강조
  - 아키텍처 메모: LLM 백엔드(cli|api) 전환 항목 신설, 라우팅 haiku/sonnet/**opus**
- **config/pipeline.json**: `"llm_model":"qwen2.5:14b"` → `"haiku"`

### 코드 정합성
- **worker/ai_worker/scene/director.py**
  - 미정의 `from config.settings import OLLAMA_MODEL` 제거 (ImportError 잠재 버그)
  - `call_ollama_raw(...)`(call_type 미지정→haiku) → `call_llm(call_type="scene_director", post_id=...)` (sonnet 라우팅으로 교정)
  - 로깅 `model_name=OLLAMA_MODEL` → `resolve_model_id(pick_model("scene_director"))` (실제 사용 모델)
- **env/docker-compose.yml**
  - `llm-worker` build context `../llm-worker`(미존재) → `../worker/llm` (실제 Spring Boot 소스, Dockerfile 존재 확인)

## 3. 테스트 결과물 저장 위치
- 별도 산출물 없음 (문서/설정/소스 수정). 변경 파일: README.md, CLAUDE.md, config/pipeline.json, worker/ai_worker/scene/director.py, env/docker-compose.yml

## 4. 수동 테스트 방법
1. `docker compose -f env/docker-compose.yml config` — YAML/빌드 컨텍스트 검증
2. `docker compose -f env/docker-compose.yml build llm-worker` — `../worker/llm` 빌드 성공 확인
3. `python -c "import ai_worker.scene.director"` (컨테이너 내) — import 오류 없음 확인
4. 게시글 1건 처리 → LLM 로그(`/admin/llm-logs`)에서 scene_director 호출 `model_name`이 sonnet 계열로 기록되는지 확인

## 5. 추천 commit message
```
docs: README/CLAUDE qwen2.5→Claude(CLI/API) 갱신 및 구조 동기화

- README 전면 재작성: LLM 백엔드(cli/api), Next.js+Spring 대시보드,
  env/ compose 단위, 11개 서비스, 프로젝트 구조
- CLAUDE.md: llm-worker(worker/llm) · telegram-bridge · 백엔드 전환 메모
- fix(scene_director): 미정의 OLLAMA_MODEL import 제거,
  call_llm(call_type="scene_director")로 교정
- fix(compose): llm-worker build context ../worker/llm 교정
- config: pipeline.json llm_model qwen2.5:14b→haiku
```
