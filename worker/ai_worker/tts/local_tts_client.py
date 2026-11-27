# 출처: /home/justant/Data/Local-TTS/client/local_tts_client.py 의 **사본**이다(앱 간 import 금지 원칙).
# 원본이 갱신되면 이 파일을 통째로 다시 복사한다. 이 사본을 직접 고치지 않는다(어댑터는 engines/local_tts.py).
# 사본 작성: 2026-11-27 (P3-①). 원본 갱신 반영: 2026-11-27 (Local-TTS 69fce05).
"""Local-TTS 참조 클라이언트 (단일 파일, 의존성: httpx 만).

앱(Flight-Brain, WaggleBot)은 이 파일을 **사본으로 복사**해 쓴다(앱 간 import 금지).
설계 기준: 00_plan.md §5.1/§5.2, 07_provider_api_design.md 설계안 A(job) + /v1/audio/speech 어댑터.

빠른 사용::

    c = LocalTTS("http://127.0.0.1:8500", client="flight-brain")
    audio = c.speech("안녕하세요.", {"voice": "M1"}).audio           # 동기, bytes
    job = c.create_job(text, {"chunk": {"mode": "sentence"}}, idempotency="fb:script:9f2c")
    st = c.wait(job["id"], on_progress=lambda s: print(s["progress"]["percent"]))
    data = c.audio(job["id"])

규칙:
  * 접수(HTTP) 오류는 예외, 접수 이후 오류는 job 상태(`failed`)로 온다 -> wait()가 JobFailedError로 변환.
  * 재시도 대상: 연결 오류·타임아웃, 429, 503(+502/504). Retry-After 가 있으면 그 값을 따른다.
    본문이 같아도 중복 job 이 생길 수 있는 POST(/v1/jobs)는 Idempotency-Key 가 있을 때만
    "연결 오류" 재시도를 한다(429/503 은 접수 거부이므로 키 없이도 재시도).
"""
from __future__ import annotations

import dataclasses
import random
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping
from urllib.parse import quote

import httpx

__all__ = [
    "LocalTTS", "SpeechResult", "Options", "NormalizeOptions", "ChunkOptions",
    "PostprocessOptions", "OutputOptions",
    "LocalTTSError", "ConnectionFailed", "RequestTimeout", "InvalidRequest", "ValidationFailed",
    "NotFound", "Conflict", "Expired", "RateLimited", "Unavailable", "ServerError",
    "JobFailed", "JobCancelled", "WaitTimeout", "SpeechTimeout",
]

TERMINAL_STATES = frozenset({"done", "failed", "cancelled"})


# ───────────────────────── 오류 계층 ─────────────────────────
class LocalTTSError(Exception):
    """모든 클라이언트 오류의 부모."""

    def __init__(self, message: str = "", *, status: int | None = None, code: str | None = None,
                 type_: str | None = None, retryable: bool = False, request_id: str | None = None,
                 details: Any = None, param: str | None = None, job_id: str | None = None,
                 retry_after: float | None = None):
        super().__init__(message)
        self.message, self.status, self.code, self.type = message, status, code, type_
        self.retryable, self.request_id, self.details = retryable, request_id, details
        self.param, self.job_id, self.retry_after = param, job_id, retry_after

    def __str__(self) -> str:
        bits = [self.message or self.__class__.__name__]
        if self.status:
            bits.append(f"[{self.status}{'/' + self.code if self.code else ''}]")
        if self.request_id:
            bits.append(f"request_id={self.request_id}")
        return " ".join(bits)


class ConnectionFailed(LocalTTSError):
    """서버에 연결하지 못함(재시도 소진 후)."""


class RequestTimeout(LocalTTSError):
    """HTTP 타임아웃(재시도 소진 후)."""


class InvalidRequest(LocalTTSError):
    """400 계열(text_too_long, empty_input, unsupported_text ...)."""


class ValidationFailed(InvalidRequest):
    """422 invalid_options / profile_validation_failed. details 에 필드별 목록."""


class NotFound(LocalTTSError):
    """404."""


class Conflict(LocalTTSError):
    """409 (idempotency_conflict, job_not_ready, job_not_resumable ...)."""


class Expired(LocalTTSError):
    """410 result_expired."""


class RateLimited(LocalTTSError):
    """429 queue_full."""


class Unavailable(LocalTTSError):
    """503 model_loading / no_gpu."""


class ServerError(LocalTTSError):
    """그 밖의 5xx."""


class JobFailed(LocalTTSError):
    """wait() 중 job 이 failed 로 종료. `.job` 에 마지막 상태."""

    def __init__(self, message: str, job: dict, **kw: Any):
        super().__init__(message, job_id=job.get("id"), **kw)
        self.job = job


class JobCancelled(JobFailed):
    """wait() 중 job 이 cancelled 로 종료."""


class WaitTimeout(LocalTTSError):
    """wait(timeout=...) 초과. job 은 서버에서 계속 진행 중일 수 있다. `.job` 에 마지막 상태."""

    def __init__(self, message: str, job: dict | None = None, **kw: Any):
        super().__init__(message, job_id=(job or {}).get("id"), **kw)
        self.job = job


class SpeechTimeout(LocalTTSError):
    """speech() 가 서버 504 timeout. job_id 로 이어받을 수 있다(job 은 계속 돈다)."""


_STATUS_EXC: dict[int, type[LocalTTSError]] = {
    400: InvalidRequest, 404: NotFound, 409: Conflict, 410: Expired,
    413: InvalidRequest, 422: ValidationFailed, 429: RateLimited, 503: Unavailable,
}


# ───────────────────────── 옵션 dataclass 헬퍼(선택) ─────────────────────────
def _prune(v: Any) -> Any:
    """None 값을 재귀 제거(서버 기본값 사용)."""
    if dataclasses.is_dataclass(v) and not isinstance(v, type):
        v = dataclasses.asdict(v)
    if isinstance(v, Mapping):
        return {k: _prune(x) for k, x in v.items() if x is not None}
    if isinstance(v, (list, tuple)):
        return [_prune(x) for x in v]
    return v


@dataclass
class NormalizeOptions:
    enabled: bool | None = None
    profile: str | None = None
    builtin: list[str] | None = None
    strip_unsupported: bool | None = None
    return_text: bool | None = None


@dataclass
class ChunkOptions:
    mode: str | None = None            # none|sentence|max_chars|delimiter|explicit
    max_chars: int | None = None
    min_chars: int | None = None
    delimiter: str | None = None
    chunker: str | None = None


@dataclass
class PostprocessOptions:
    chunk: dict[str, Any] | None = None     # {"trim_silence":{...},"fade_ms":10,"tempo":1.0}
    gap_ms: float | None = None
    para_gap_ms: float | None = None
    loudnorm: dict[str, Any] | None = None  # {"enabled":True,"i":-16,"tp":-1.5,"two_pass":True}
    sample_rate: int | None = None


@dataclass
class OutputOptions:
    format: str | None = None          # wav|mp3|flac|opus
    bitrate: str | None = None
    return_: list[str] | None = None   # ["final","chunks"] (JSON 키 "return")
    timings: bool | None = None


@dataclass
class Options:
    """plan §5.2 옵션 객체. 지정하지 않은(None) 필드는 전송하지 않는다 = 서버 기본(전 단계 OFF)."""
    voice: str | None = None
    lang: str | None = None
    speed: float | None = None
    steps: int | None = None
    seed: int | None = None
    normalize: NormalizeOptions | None = None
    chunk: ChunkOptions | None = None
    postprocess: PostprocessOptions | None = None
    output: OutputOptions | None = None
    cache: str | None = None           # use|bypass|refresh
    on_chunk_error: str | None = None  # fail|skip|retry
    ttl_sec: int | None = None
    lane: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)   # 서버가 추가하는 키(이스케이프 해치)

    def to_dict(self) -> dict[str, Any]:
        d = {f.name: getattr(self, f.name) for f in dataclasses.fields(self) if f.name != "extra"}
        out = _prune(d)
        if "output" in out and "return_" in out["output"]:
            out["output"]["return"] = out["output"].pop("return_")
        out.update(self.extra)
        return out


def _opts(options: Mapping[str, Any] | Options | None) -> dict[str, Any]:
    if options is None:
        return {}
    if isinstance(options, Options):
        return options.to_dict()
    return _prune(dict(options))


@dataclass
class SpeechResult:
    audio: bytes
    content_type: str
    headers: dict[str, str]

    @property
    def job_id(self) -> str | None:
        return self.headers.get("x-job-id") or self.headers.get("x-speech-id")

    def _f(self, name: str) -> float | None:
        v = self.headers.get(name)
        try:
            return float(v) if v is not None else None
        except ValueError:
            return None

    @property
    def duration_sec(self) -> float | None:
        return self._f("x-duration-sec")

    @property
    def queue_wait_ms(self) -> float | None:
        return self._f("x-queue-wait-ms")

    @property
    def synth_ms(self) -> float | None:
        return self._f("x-synth-ms")


def _idem_key(idempotency: str | bool | None, request_id: str | None) -> str | None:
    """Idempotency-Key 결정. 서버는 헤더 키와 options.request_id 가 다르면 400 이므로 둘을 항상 일치시킨다.

    request_id 가 있으면 그 값이 키다(idempotency=True/None 이면 자동 사용, 다른 문자열을 주면 ValueError).
    request_id 가 없으면 True=uuid 자동 생성, 문자열=그대로, None/False=키 없음."""
    if request_id:
        if isinstance(idempotency, str) and idempotency != request_id:
            raise ValueError("idempotency 와 request_id 는 같아야 합니다(서버는 둘이 다르면 400). "
                             "request_id 만 지정하면 그 값이 Idempotency-Key 로도 쓰입니다")
        return None if idempotency is False else request_id
    return str(uuid.uuid4()) if idempotency is True else (idempotency or None)


# ───────────────────────── 클라이언트 ─────────────────────────
class LocalTTS:
    def __init__(self, base_url: str = "http://127.0.0.1:8500", *, client: str | None = None,
                 token: str | None = None, timeout: float = 30.0, connect_timeout: float = 5.0,
                 max_retries: int = 5, backoff_base: float = 0.5, backoff_max: float = 30.0,
                 retry_after_max: float = 120.0, headers: Mapping[str, str] | None = None,
                 transport: httpx.BaseTransport | None = None,
                 sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.monotonic):
        """timeout: 일반 요청 read 타임아웃(초). long-poll/동기 합성은 요청별로 늘린다.
        max_retries: 첫 시도 이후 추가 재시도 횟수. sleep/clock/transport 는 테스트 주입용."""
        h = {"User-Agent": "local-tts-client/1"}
        if client:
            h["X-Client-Id"] = client
        if token:
            h["Authorization"] = f"Bearer {token}"
        h.update(headers or {})
        self.base_url = base_url.rstrip("/")
        self.timeout, self.connect_timeout = timeout, connect_timeout
        self.max_retries, self.backoff_base, self.backoff_max = max_retries, backoff_base, backoff_max
        self.retry_after_max = retry_after_max
        self._sleep, self._clock = sleep, clock
        self._http = httpx.Client(base_url=self.base_url, headers=h, transport=transport,
                                  timeout=httpx.Timeout(timeout, connect=connect_timeout))

    # --- 수명 ---
    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "LocalTTS":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    # --- 저수준 ---
    def _delay(self, attempt: int, retry_after: float | None) -> float:
        if retry_after is not None:
            return min(max(retry_after, 0.0), self.retry_after_max)
        cap = min(self.backoff_max, self.backoff_base * (2 ** attempt))
        return random.uniform(cap / 2, cap)      # equal jitter

    @staticmethod
    def _retry_after(resp: httpx.Response) -> float | None:
        v = resp.headers.get("retry-after")
        if v is None:
            return None
        try:
            return float(v)
        except ValueError:
            return None     # HTTP-date 형식은 서버가 쓰지 않음(초 단위만 지원)

    def _error(self, resp: httpx.Response) -> LocalTTSError:
        body: Any = None
        try:
            body = resp.json()
        except Exception:
            pass
        err: dict[str, Any] = {}
        if isinstance(body, dict):
            e = body.get("error")
            if isinstance(e, dict):
                err = e
            elif "detail" in body:          # FastAPI 기본 422/404 형식 대비
                err = {"message": str(body["detail"])[:500], "details": body["detail"]}
        status = resp.status_code
        exc_cls = _STATUS_EXC.get(status) or (ServerError if status >= 500 else LocalTTSError)
        code = err.get("code")
        if status == 504 and code == "timeout":
            exc_cls = SpeechTimeout
        det = err.get("details")
        job_id = err.get("job_id") or (det.get("job_id") if isinstance(det, dict) else None)
        return exc_cls(err.get("message") or resp.text[:300] or f"HTTP {status}",
                       status=status, code=code, type_=err.get("type"),
                       retryable=bool(err.get("retryable", status in (429, 503))),
                       request_id=err.get("request_id") or resp.headers.get("x-request-id"),
                       details=err.get("details"), param=err.get("param"), job_id=job_id,
                       retry_after=self._retry_after(resp))

    def _request(self, method: str, path: str, *, params: Mapping[str, Any] | None = None,
                 json: Any = None, headers: Mapping[str, str] | None = None,
                 timeout: float | None = None, safe_retry: bool = True,
                 expect: Iterable[int] | None = None, raw: bool = False,
                 max_retries: int | None = None) -> httpx.Response:
        """safe_retry=False: 연결/타임아웃 오류는 재시도하지 않는다(중복 생성 위험). 429/503 은 항상 재시도."""
        retries = self.max_retries if max_retries is None else max_retries
        t = httpx.Timeout(timeout if timeout is not None else self.timeout, connect=self.connect_timeout)
        params = {k: v for k, v in (params or {}).items() if v is not None}
        last: LocalTTSError | None = None
        for attempt in range(retries + 1):
            try:
                resp = self._http.request(method, path, params=params or None, json=json,
                                          headers=dict(headers or {}), timeout=t)
            except httpx.TimeoutException as e:
                last = RequestTimeout(f"{method} {path} 타임아웃: {e}")
                if not safe_retry:
                    raise last from e
            except httpx.TransportError as e:
                last = ConnectionFailed(f"{method} {path} 연결 실패: {e}")
                if not safe_retry:
                    raise last from e
            else:
                ok = resp.status_code in expect if expect else resp.status_code < 400
                if ok:
                    return resp
                exc = self._error(resp)
                transient = resp.status_code in (429, 503) or (
                    safe_retry and resp.status_code in (502, 504) and not isinstance(exc, SpeechTimeout))
                if not transient or attempt >= retries:
                    raise exc
                last = exc
            if attempt >= retries:
                break
            self._sleep(self._delay(attempt, getattr(last, "retry_after", None)))
        assert last is not None
        raise last

    def _json(self, method: str, path: str, **kw: Any) -> Any:
        resp = self._request(method, path, **kw)
        return resp.json() if resp.content else None

    # ───────────── jobs ─────────────
    def create_job(self, text: str | list[str], options: Mapping[str, Any] | Options | None = None, *,
                   request_id: str | None = None, idempotency: str | bool | None = None,
                   metadata: Mapping[str, Any] | None = None, wait: float | None = None) -> dict:
        """job 생성(202). text 가 list 면 `texts`(=explicit 청크)로 보낸다.

        idempotency: 문자열이면 Idempotency-Key 헤더, True 면 uuid 자동 생성(재시도 안전).
            request_id 를 주면 그 값이 곧 키다(서버는 헤더와 options.request_id 가 다르면 400).
        wait: 지정 시 서버가 최대 wait초 대기 후 완료되면 200 으로 결과를 반환(?wait=N).
        """
        body: dict[str, Any] = {"texts": list(text)} if isinstance(text, (list, tuple)) else {"input": text}
        body["options"] = _opts(options)
        if request_id:                      # 서버는 최상위가 아니라 options.request_id 로 받는다(extra=forbid)
            body["options"] = {**body["options"], "request_id": request_id}
        if metadata:
            body["metadata"] = dict(metadata)
        key = _idem_key(idempotency, request_id)
        headers = {"Idempotency-Key": key} if key else {}
        if request_id:
            headers["X-Request-Id"] = request_id
        return self._json("POST", "/v1/jobs", json=body, headers=headers, safe_retry=bool(key),
                          params={"wait": wait}, expect=(200, 202),
                          timeout=(self.timeout + wait) if wait else None)

    def dry_run(self, text: str | list[str], options: Mapping[str, Any] | Options | None = None) -> dict:
        """정규화·청크까지만 실행(합성 없음). 부작용이 없으므로 재시도 안전."""
        body: dict[str, Any] = {"texts": list(text)} if isinstance(text, (list, tuple)) else {"input": text}
        body["options"] = _opts(options)
        return self._json("POST", "/v1/jobs:dry_run", json=body, expect=(200, 202))

    def get_status(self, job_id: str, *, wait: float | None = None, since_rev: int | None = None) -> dict:
        """job 상태. wait 지정 시 long-poll(변경 없으면 최대 wait초 대기)."""
        return self._json("GET", f"/v1/jobs/{job_id}", params={"wait": wait, "since_rev": since_rev},
                          timeout=(self.timeout + wait) if wait else None)

    def list_jobs(self, *, state: str | None = None, client: str | None = None,
                  since: str | None = None, limit: int | None = None) -> list[dict]:
        r = self._json("GET", "/v1/jobs", params={"state": state, "client": client,
                                                  "since": since, "limit": limit})
        return r["data"] if isinstance(r, dict) and "data" in r else r

    def chunks(self, job_id: str, *, start: int = 0, limit: int = 50, all: bool = True) -> list[dict]:
        """청크 목록. all=True 면 total 까지 페이지네이션(from/limit)해 전부 모은다."""
        out: list[dict] = []
        pos = start
        while True:
            r = self._json("GET", f"/v1/jobs/{job_id}/chunks", params={"from": pos, "limit": limit})
            data = r["data"] if isinstance(r, dict) else r
            out.extend(data)
            total = r.get("total") if isinstance(r, dict) else None
            pos += len(data)
            if not all or not data or total is None or pos >= total:
                return out

    def chunk_audio(self, job_id: str, index: int) -> bytes:
        return self._request("GET", f"/v1/jobs/{job_id}/chunks/{index}/audio").content

    def audio(self, job_id: str, *, partial: bool = False) -> bytes:
        """최종 오디오. 미완료면 Conflict(job_not_ready). partial=True 는 끝난 청크만 이어 붙임."""
        return self._request("GET", f"/v1/jobs/{job_id}/audio",
                             params={"partial": "true" if partial else None},
                             timeout=max(self.timeout, 120.0)).content

    def save_audio(self, job_id: str, path: str | Path, *, partial: bool = False) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + ".part")
        tmp.write_bytes(self.audio(job_id, partial=partial))
        tmp.replace(p)
        return p

    def timings(self, job_id: str) -> dict:
        return self._json("GET", f"/v1/jobs/{job_id}/timings")

    def cancel(self, job_id: str) -> dict:
        return self._json("POST", f"/v1/jobs/{job_id}:cancel", expect=(200, 202))

    def resume(self, job_id: str) -> dict:
        """failed/cancelled job 의 미완료 청크만 재큐(큐 맨 뒤)."""
        return self._json("POST", f"/v1/jobs/{job_id}:resume", expect=(200, 202))

    def delete(self, job_id: str) -> None:
        self._request("DELETE", f"/v1/jobs/{job_id}", expect=(200, 202, 204))

    def wait(self, job_id: str, *, timeout: float | None = None, poll_interval: float = 1.0,
             long_poll: float | None = 25.0, on_progress: Callable[[dict], None] | None = None,
             raise_on_failure: bool = True) -> dict:
        """종료 상태(done/failed/cancelled)까지 대기해 마지막 상태를 반환.

        long_poll: 초 단위(None/0 이면 순수 polling). 서버가 wait 를 무시해 즉시 같은 rev 를 돌려주면
        poll_interval 이상 간격을 유지한다(서버를 두드리지 않음). timeout 초과 시 WaitTimeout(서버 job 은 유지).
        raise_on_failure: failed -> JobFailed, cancelled -> JobCancelled.
        """
        deadline = None if timeout is None else self._clock() + timeout
        since: int | None = None
        job: dict | None = None
        while True:
            remaining = None if deadline is None else deadline - self._clock()
            if remaining is not None and remaining <= 0:
                raise WaitTimeout(f"job {job_id} 대기 {timeout}s 초과", job)
            lp = long_poll if long_poll else None
            if lp is not None and remaining is not None:
                lp = min(lp, max(remaining, 0.0))
            t0 = self._clock()
            job = self.get_status(job_id, wait=lp, since_rev=since)
            if on_progress and (since is None or job.get("rev") != since):
                on_progress(job)
            state = job.get("state")
            if state in TERMINAL_STATES:
                if raise_on_failure and state != "done":
                    err = job.get("error") or {}
                    cls = JobCancelled if state == "cancelled" else JobFailed
                    raise cls(err.get("message") or f"job {job_id} {state}", job,
                              code=err.get("code"), retryable=bool(err.get("retryable")))
                return job
            since = job.get("rev", since)
            # long-poll 이 즉시 돌아왔다면(미지원/잦은 변경) 최소 poll_interval 간격을 유지한다.
            elapsed = self._clock() - t0
            if elapsed < poll_interval:
                d = poll_interval - elapsed
                if deadline is not None:
                    d = min(d, max(deadline - self._clock(), 0.0))
                self._sleep(d)

    def synthesize(self, text: str | list[str], options: Mapping[str, Any] | Options | None = None, *,
                   timeout: float | None = None, request_id: str | None = None,
                   idempotency: str | bool | None = True, on_progress: Callable[[dict], None] | None = None,
                   poll_interval: float = 2.0) -> tuple[bytes, dict]:
        """create_job + wait + audio. (오디오 bytes, 최종 job 상태). 장문용 편의 함수."""
        job = self.create_job(text, options, request_id=request_id, idempotency=idempotency)
        st = self.wait(job["id"], timeout=timeout, on_progress=on_progress, poll_interval=poll_interval)
        return self.audio(job["id"]), st

    # ───────────── 동기 speech (OpenAI 호환 어댑터) ─────────────
    def speech(self, text: str, options: Mapping[str, Any] | Options | None = None, *,
               model: str = "supertonic-3", timeout: float = 150.0, request_id: str | None = None,
               idempotency: str | bool | None = None) -> SpeechResult:
        """POST /v1/audio/speech. 본문=오디오 바이트, 부가정보는 X-* 헤더(SpeechResult).

        options 는 §5.2 옵션 객체 그대로 받는다. voice/speed/output.format 은 OpenAI 표준 필드로도 보내고
        local_tts 에도 그대로 둔다(표준 필드 우선). 서버 504(timeout)는 SpeechTimeout(job_id 포함).
        합성은 부작용이 없고 비용이 있으므로 연결 오류 재시도는 idempotency 지정 시에만 한다.
        """
        o = _opts(options)
        fmt = (o.get("output") or {}).get("format") or "wav"
        body: dict[str, Any] = {"model": model, "input": text, "response_format": fmt, "local_tts": o}
        if "voice" in o:
            body["voice"] = o["voice"]
        if "speed" in o:
            body["speed"] = o["speed"]
        key = _idem_key(idempotency, request_id)
        headers = {"Idempotency-Key": key} if key else {}
        if request_id:
            body["local_tts"] = {**o, "request_id": request_id}
            headers["X-Request-Id"] = request_id
        resp = self._request("POST", "/v1/audio/speech", json=body, headers=headers,
                             timeout=timeout, safe_retry=bool(key))
        return SpeechResult(resp.content, resp.headers.get("content-type", ""),
                            {k.lower(): v for k, v in resp.headers.items()})

    # ───────────── profiles ─────────────
    @staticmethod
    def _pid(pid: str) -> str:
        return quote(pid, safe="/")      # "flight-brain" 또는 "flight-brain/aviation-ko" 모두 허용

    def put_profile(self, pid: str, meta: Mapping[str, Any]) -> dict:
        return self._json("PUT", f"/v1/profiles/{self._pid(pid)}", json=dict(meta), expect=(200, 201))

    def list_profiles(self) -> list[dict]:
        r = self._json("GET", "/v1/profiles")
        return r["data"] if isinstance(r, dict) and "data" in r else r

    def get_profile(self, pid: str) -> dict:
        return self._json("GET", f"/v1/profiles/{self._pid(pid)}")

    def upload_profile(self, pid: str, document: Mapping[str, Any], *, activate: bool = False,
                       force_warnings: bool = False) -> dict:
        """새 버전 업로드(항상 draft). 서버 업로드 엔드포인트는 활성화를 하지 않으므로(쿼리 무시),
        activate=True 면 업로드 뒤 `activate_profile` 을 따로 호출한다(서버가 검증을 수행, 실패 시 ValidationFailed).
        반환: 업로드 응답 dict. 활성화했으면 `activation` 키에 활성화 응답이 붙는다."""
        out = self._json("POST", f"/v1/profiles/{self._pid(pid)}/versions", json=dict(document), expect=(200, 201))
        if activate:
            out = {**out, "activation": self.activate_profile(pid, int(out["version"]), force_warnings=force_warnings)}
        return out

    def list_versions(self, pid: str) -> list[dict]:
        r = self._json("GET", f"/v1/profiles/{self._pid(pid)}/versions")
        return r["data"] if isinstance(r, dict) and "data" in r else r

    def get_version(self, pid: str, version: int) -> dict:
        return self._json("GET", f"/v1/profiles/{self._pid(pid)}/versions/{version}")

    def validate_profile(self, pid: str, version: int) -> dict:
        return self._json("POST", f"/v1/profiles/{self._pid(pid)}/versions/{version}:validate")

    def preview_profile(self, pid: str, version: int, text: str, *, diff: bool = True) -> dict:
        """정규화 미리보기(텍스트만). 서버는 오디오 미리듣기를 지원하지 않는다(미지 키는 422)."""
        body: dict[str, Any] = {"input": text, "diff": diff}
        return self._json("POST", f"/v1/profiles/{self._pid(pid)}/versions/{version}:preview", json=body)

    def activate_profile(self, pid: str, version: int, *, force_warnings: bool = False) -> dict:
        return self._json("POST", f"/v1/profiles/{self._pid(pid)}/versions/{version}:activate",
                          params={"force_warnings": "true" if force_warnings else None})

    def rollback_profile(self, pid: str, to: int | None = None) -> dict:
        return self._json("POST", f"/v1/profiles/{self._pid(pid)}:rollback",
                          json={"to": to} if to is not None else None)

    def delete_version(self, pid: str, version: int) -> None:
        self._request("DELETE", f"/v1/profiles/{self._pid(pid)}/versions/{version}",
                      expect=(200, 202, 204))

    # ───────────── voices / 운영 ─────────────
    def voices(self) -> list[dict]:
        r = self._json("GET", "/v1/voices")
        return r["data"] if isinstance(r, dict) and "data" in r else r

    def defaults(self) -> dict:
        return self._json("GET", "/v1/defaults")

    def status(self) -> dict:
        return self._json("GET", "/v1/status")

    def healthy(self) -> bool:
        """/healthz 1회 확인(재시도 없음). 예외를 던지지 않는다."""
        try:
            return self._request("GET", "/healthz", max_retries=0, timeout=3.0).status_code == 200
        except LocalTTSError:
            return False

    def ready(self) -> bool:
        """/readyz 1회 확인(모델 로드·DB 접근). 예외를 던지지 않는다."""
        try:
            return self._request("GET", "/readyz", max_retries=0, timeout=3.0).status_code == 200
        except LocalTTSError:
            return False
