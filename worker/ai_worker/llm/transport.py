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


# ---------------------------------------------------------------------------
# LLM 백엔드 선택: "cli"(llm-worker 브릿지) | "api"(Anthropic API 직접)
#   - 대시보드 설정(pipeline.json)의 llm_backend 키로 전환
#   - API 키는 env ANTHROPIC_API_KEY → config/credentials.json["anthropic_api_key"] 순
# ---------------------------------------------------------------------------
_ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
_ANTHROPIC_VERSION = "2023-06-01"
_API_DEFAULT_MAX_TOKENS = 8192


def _get_llm_backend() -> str:
    try:
        from config.settings import load_pipeline_config
        return str(load_pipeline_config().get("llm_backend", "cli")).strip().lower()
    except Exception:
        return "cli"


def _get_anthropic_api_key() -> str | None:
    import os
    key = os.getenv("ANTHROPIC_API_KEY")
    if key and key.strip():
        return key.strip()
    try:
        from config.settings import load_credentials_config
        val = load_credentials_config().get("anthropic_api_key")
        if isinstance(val, str) and val.strip():
            return val.strip()
    except Exception:
        pass
    return None


def _call_via_api(
    prompt: str,
    *,
    resolved_model: str,
    max_tokens: int,
    temperature: float,
    json_mode: bool,
    timeout: int,
) -> str:
    """Anthropic Messages API 직접 호출. 원시 텍스트 반환."""
    api_key = _get_anthropic_api_key()
    if not api_key:
        raise RuntimeError(
            "Claude API 백엔드가 선택됐지만 API 키가 없습니다. "
            "대시보드(/admin/settings)에서 Anthropic API 키를 입력하거나 "
            "env/.env에 ANTHROPIC_API_KEY를 설정하세요."
        )
    # CLI는 max_tokens를 무시했으므로, API에서 잘림 방지를 위해 충분히 큰 값 보장
    api_max = max_tokens if max_tokens and max_tokens >= 2048 else _API_DEFAULT_MAX_TOKENS
    body: dict = {
        "model": resolved_model,
        "max_tokens": api_max,
        "temperature": temperature,
        "messages": [{"role": "user", "content": prompt}],
    }
    if json_mode:
        body["system"] = "Respond ONLY with valid JSON. No markdown, no code fences, no prose."
    headers = {
        "x-api-key": api_key,
        "anthropic-version": _ANTHROPIC_VERSION,
        "content-type": "application/json",
    }
    try:
        resp = _session.post(
            _ANTHROPIC_API_URL, json=body, headers=headers, timeout=(10, timeout + 30)
        )
    except requests.Timeout:
        raise TimeoutError(f"Anthropic API 응답 타임아웃 ({timeout}초 초과)")
    except requests.RequestException as e:
        raise ConnectionError(f"Anthropic API 연결 오류: {e}") from e
    if resp.status_code == 401:
        raise RuntimeError("Anthropic API 인증 실패(401) — API 키를 확인하세요.")
    if resp.status_code == 429:
        raise RuntimeError("Anthropic API 사용량 한도 초과(429) — 잠시 후 재시도하세요.")
    resp.raise_for_status()
    data = resp.json()
    parts = data.get("content", []) or []
    text = "".join(p.get("text", "") for p in parts if p.get("type") == "text")
    return text.strip()


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
    """LLM 호출. 원시 텍스트 반환.

    백엔드는 대시보드 설정(llm_backend)에 따라 전환:
      - "cli": llm-worker(claude CLI 브릿지) — temperature/max_tokens는 advisory
      - "api": Anthropic API 직접 호출
    """
    resolved_model = resolve_model_id(pick_model(call_type, model))

    if _get_llm_backend() == "api":
        logger.debug("LLM 백엔드=api (model=%s, call_type=%s)", resolved_model, call_type)
        return _call_via_api(
            prompt,
            resolved_model=resolved_model,
            max_tokens=max_tokens,
            temperature=temperature,
            json_mode=json_mode,
            timeout=timeout,
        )

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
