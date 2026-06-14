# LLM 안전 규칙 — WaggleBot

항상 로드. 위반 시 코드 리뷰에서 reject.

## LLM 호출 안전 규칙

- **모든 LLM 호출은 `call_llm()` / `call_llm_raw()`만** → `worker/ai_worker/llm/transport.py`
- 직접 HTTP 호출 절대 금지 (`requests.post("https://api.anthropic.com/...")` 등)
- **Ollama / qwen2.5 / 로컬 LLM 사용 금지** — Claude(haiku/sonnet)만
- `call_ollama_raw`는 레거시 별칭 — 신규 코드에서 사용 금지

## 파이프라인 독립 규칙

- `ai_worker/video/` 에서 `ai_worker/tts/` **절대 import 금지** — 독립 파이프라인
- `ScriptData`는 `from db.models import ScriptData` (canonical 위치)

## JSON 파싱 주의

- LLM 프록시(llm-worker)는 `jsonMode` 무시·코드펜스 첨부 가능
- Python 측에서 항상 `extract_json_object()`로 파싱할 것
- `jsonValid=false` 응답도 텍스트 파싱 시도 필수
