"""Claude llm-worker HTTP 트랜스포트.

Ollama를 완전히 대체. 공개 API는 기존 client.py와 동일하게 유지.
claude CLI는 temperature/max_tokens를 지원하지 않으므로 advisory로만 처리.
"""
from __future__ import annotations

import json
import logging

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

_MODEL_ALIASES: dict[str, str] = {
    "haiku": "claude-haiku-4-5-20251001",
    "sonnet": "claude-sonnet-4-6",
    "opus": "claude-opus-4-8",
}

_CALL_TYPE_MODEL_MAP: dict[str, str] = {
    "chunk": "sonnet",
    "generate_script": "sonnet",
    "generate_script_editor": "sonnet",
    "generate_script_auto": "sonnet",
    "scene_director": "sonnet",
    "feedback_insights": "sonnet",
    "comment_summarize": "haiku",
    "video_prompt_t2v": "haiku",
    "video_prompt_i2v": "haiku",
    "video_prompt_simplify": "haiku",
    "translate": "haiku",
    "raw": "haiku",
}


def resolve_model_id(name: str | None) -> str:
    if not name:
        return _MODEL_ALIASES.get(_get_default_model(), "claude-haiku-4-5-20251001")
    if name.startswith("claude-"):
        return name
    return _MODEL_ALIASES.get(name, name)


def _get_default_model() -> str:
    try:
        from config.settings import DEFAULT_LLM_MODEL
        return DEFAULT_LLM_MODEL
    except ImportError:
        return "haiku"


def pick_model(call_type: str, explicit: str | None = None) -> str:
    if explicit:
        return explicit
    try:
        from config.settings import load_pipeline_config
        cfg = load_pipeline_config()
        overrides_raw = cfg.get("llm_model_overrides", "{}")
        overrides = json.loads(overrides_raw) if isinstance(overrides_raw, str) else overrides_raw
        if call_type in overrides:
            return overrides[call_type]
    except Exception:
        pass
    if call_type in _CALL_TYPE_MODEL_MAP:
        return _CALL_TYPE_MODEL_MAP[call_type]
    try:
        from config.settings import load_pipeline_config
        return load_pipeline_config().get("llm_model", _get_default_model())
    except Exception:
        return _get_default_model()


def _build_session() -> requests.Session:
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


_session = _build_session()


def _get_worker_url() -> str:
    from config.settings import LLM_WORKER_URL
    return LLM_WORKER_URL


def call_llm(
    prompt: str,
    *,
    model: str | None = None,
    max_tokens: int = 512,
    temperature: float = 0.5,
    json_mode: bool = False,
    call_type: str = "raw",
    timeout: int = 120,
    post_id: int | None = None,
) -> str:
    """llm-worker HTTP API 호출. 원시 텍스트 반환.

    Note: claude CLI는 temperature/max_tokens 미지원 — advisory only.
    """
    resolved_model = resolve_model_id(pick_model(call_type, model))
    payload = {
        "prompt": prompt,
        "model": resolved_model,
        "jsonMode": json_mode,
        "maxTokens": max_tokens,
        "temperature": temperature,
        "callType": call_type,
        "correlationId": f"post-{post_id}" if post_id else None,
        "timeoutMs": timeout * 1000,
    }
    url = _get_worker_url() + "/v1/invoke"
    try:
        resp = _session.post(url, json=payload, timeout=(10, timeout + 30))
        resp.raise_for_status()
        data = resp.json()
        return data.get("text", "").strip()
    except requests.Timeout:
        raise TimeoutError(f"llm-worker 응답 타임아웃 ({timeout}초 초과)")
    except requests.RequestException as e:
        raise ConnectionError(f"llm-worker 연결 오류: {e}") from e


def call_llm_json(
    prompt: str,
    *,
    model: str | None = None,
    call_type: str = "chunk",
    timeout: int = 180,
    post_id: int | None = None,
) -> dict:
    """JSON 모드 llm-worker 호출. dict 반환."""
    import re
    raw = call_llm(
        prompt,
        model=model,
        json_mode=True,
        call_type=call_type,
        timeout=timeout,
        post_id=post_id,
    )
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("JSON 파싱 실패, 정규식 폴백: %s...", raw[:100])
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        return {}


# 하위 호환 별칭
call_llm_raw = call_llm
