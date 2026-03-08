import logging

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config.settings import get_ollama_host, get_domain_setting, OLLAMA_MODEL
from db.models import ScriptData  # re-export — 기존 import 경로 호환
from ai_worker.script.parser import parse_script_json
from ai_worker.script.normalizer import ensure_comments

logger = logging.getLogger(__name__)


def _build_ollama_session() -> requests.Session:
    """재시도 전략이 포함된 requests 세션 생성."""
    session = requests.Session()
    retry = Retry(
        total=2,
        backoff_factor=1,
        status_forcelist=[500, 502, 503, 504],
        allowed_methods=["POST"],
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


# 모듈 레벨 세션 (재사용으로 커넥션 풀 활용)
_ollama_session = _build_ollama_session()


# ---------------------------------------------------------------------------
# 프롬프트 — settings.yaml 공통 페르소나·규칙 로드
# ---------------------------------------------------------------------------

_PERSONA: str = get_domain_setting("script", "prompt", "persona", default="")
_RULES: str = get_domain_setting("script", "prompt", "rules", default="")

_OUTPUT_FORMAT_GENERATE = """\
## 출력 형식 (JSON)
{{
  "hook": "시청자가 스크롤을 멈출 도발적인 한 줄 (15자 이내)",
  "body": [
    {{
      "type": "body",
      "line_count": 2,
      "lines": ["호흡 단위로 자연스럽게 끊은 앞부분", "이어지는 자연스러운 뒷부분"]
    }},
    {{
      "type": "body",
      "line_count": 1,
      "lines": ["단어 중간에 끊기지 않은 한 줄"]
    }},
    {{
      "type": "comment",
      "author": "닉네임",
      "line_count": 2,
      "lines": ["베댓의 내용만 호흡에 맞춰", "자연스럽게 분할하여 작성"]
    }}
  ],
  "closer": "여러분들의 생각은 어떤가요?",
  "title_suggestion": "원문 제목 그대로 기입 (수정 절대 금지)",
  "tags": ["태그1", "태그2", "태그3"],
  "mood": "daily"
}}"""


def _build_generate_prompt(title: str, body: str, comments: str) -> str:
    """generate_script용 전체 프롬프트를 조립한다."""
    return (
        f"{_PERSONA}\n"
        f"## 입력\n"
        f"- 제목: {title}\n"
        f"- 본문: {body}\n"
        f"- 베스트 댓글: {comments}\n\n"
        f"{_OUTPUT_FORMAT_GENERATE}\n\n"
        f"{_RULES}"
    )

# ---------------------------------------------------------------------------
# 내부 헬퍼
# ---------------------------------------------------------------------------

def _call_ollama(prompt: str, model: str, num_predict: int = 400, timeout: int = 180) -> str:
    url = f"{get_ollama_host()}/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"num_predict": num_predict, "temperature": 0.7},
    }
    try:
        resp = _ollama_session.post(url, json=payload, timeout=(10, timeout))
        resp.raise_for_status()
        return resp.json().get("response", "").strip()
    except requests.Timeout:
        raise TimeoutError(f"Ollama 응답 타임아웃 ({timeout}초 초과)")
    except requests.RequestException as e:
        raise ConnectionError(f"Ollama 연결 오류: {e}") from e


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_script(
    title: str,
    body: str,
    comments: list[str],
    *,
    model: str | None = None,
    extra_instructions: str | None = None,
    post_id: int | None = None,
    call_type: str = "generate_script",
) -> ScriptData:
    """구조화 대본(ScriptData) 생성.

    Args:
        extra_instructions: 프롬프트 끝에 추가할 보조 지시사항 (스타일, 톤 등).
        post_id:            LLM 로그 연결용 게시글 ID (선택).
        call_type:          LLM 로그 호출 유형 (기본 "generate_script",
                            대시보드 편집실은 "generate_script_editor").
    """
    from ai_worker.script.logger import LLMCallTimer, log_llm_call

    model = model or OLLAMA_MODEL
    prompt = _build_generate_prompt(
        title=title,
        body=body[:4000],
        comments="\n".join(f"- {c}" for c in comments[:5]),
    )

    if extra_instructions and extra_instructions.strip():
        prompt += f"\n\n## 추가 지시사항\n{extra_instructions.strip()}"

    logger.info("Ollama 대본 생성 요청: model=%s (extra=%s)", model, bool(extra_instructions))

    raw = ""

    # ── LLM 호출 ──
    # with 블록 밖에서 log_llm_call을 호출해야 timer.elapsed_ms가 정확함
    try:
        with LLMCallTimer() as timer:
            raw = _call_ollama(prompt, model, num_predict=2048, timeout=300)
    except Exception as exc:
        # 실패 로그 기록 (timer.__exit__ 완료 후이므로 elapsed_ms 정확)
        logger.error("Ollama 호출 실패: %s", exc)
        log_llm_call(
            call_type=call_type,
            post_id=post_id,
            model_name=model,
            prompt_text=prompt,
            raw_response=raw,
            success=False,
            error_message=str(exc),
            content_length=len(body),
            duration_ms=timer.elapsed_ms,
        )
        raise

    logger.info("Ollama 응답 수신: %d자 (%dms)", len(raw), timer.elapsed_ms)

    # ── 파싱 ──
    script = parse_script_json(raw)
    script = ensure_comments(script, comments, post_id=post_id)

    # ── 성공 로그 기록 (파싱 완료 후 — parsed_result + duration_ms 정확) ──
    log_llm_call(
        call_type=call_type,
        post_id=post_id,
        model_name=model,
        prompt_text=prompt,
        raw_response=raw,
        parsed_result={"hook": script.hook, "body": script.body,
                       "closer": script.closer, "mood": script.mood,
                       "tags": script.tags},
        image_count=0,
        content_length=len(body),
        success=True,
        duration_ms=timer.elapsed_ms,
    )

    logger.info("대본 생성 완료: hook=%s...", script.hook[:30])
    return script



def call_ollama_raw(
    prompt: str,
    model: str | None = None,
    max_tokens: int = 512,
    temperature: float = 0.5,
    timeout: int = 120,
) -> str:
    """범용 Ollama API 호출. JSON 파싱 없이 원시 응답 반환.

    Args:
        prompt: 프롬프트 전체 텍스트
        model: Ollama 모델명 (None이면 기본값)
        max_tokens: 최대 토큰 수
        temperature: 샘플링 온도
        timeout: 읽기 타임아웃 (초, 기본 2분)

    Returns:
        LLM 원시 응답 텍스트
    """
    _model = model or OLLAMA_MODEL
    raw = _call_ollama(prompt, _model, num_predict=max_tokens, timeout=timeout)
    return raw
