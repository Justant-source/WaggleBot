"""OpenAudio S1-mini TTS 클라이언트 (fish-speech API 서버, ADR-0005).

실행 방식: HTTP API 서버(fish-speech 컨테이너)의 /v1/tts 호출.
참조 오디오: assets/voices/<key>/ 폴더(NN.wav+NN.lab) → reference_id 클로닝.
             폴더 부재 시 레거시 평면 파일 base64 폴백.
감정 표현: tts_emotion → S1 인라인 감정 마커 주입.
"""
import asyncio
import base64
import concurrent.futures
import hashlib
import json
import logging
import re
import subprocess
import tempfile
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

import httpx

# Fish Speech 서버는 단일 GPU 모델이므로 동시 요청을 처리하지 못한다.
# render_stage(스레드 풀)와 llm_tts_stage(메인 이벤트 루프)가 동시에 요청을 보내면
# baize.ClientDisconnect 오류가 발생하므로, threading.Lock으로 전역 직렬화한다.
_FISH_SPEECH_LOCK = threading.Lock()
# Waiting on a ``threading.Lock`` in the default executor can starve ASR jobs:
# every concurrently queued synthesis occupies a worker while waiting for the
# Fish request that itself awaits CPU ASR.  Keep the cross-event-loop lock (the
# renderer can create a loop in another thread), but isolate its one blocking
# waiter from the shared executor.
_FISH_SPEECH_LOCK_EXECUTOR = concurrent.futures.ThreadPoolExecutor(
    max_workers=1,
    thread_name_prefix="fish-speech-lock",
)

from config.settings import (
    FISH_SPEECH_CHUNK_LENGTH,
    FISH_SPEECH_NORMALIZE,
    FISH_SPEECH_REPETITION_PENALTY,
    FISH_SPEECH_SEED,
    FISH_SPEECH_TEMPERATURE,
    FISH_SPEECH_TIMEOUT,
    FISH_SPEECH_TOP_P,
    FISH_SPEECH_URL,
    FISH_SPEECH_USE_MEMORY_CACHE,
    TTS_EMOTION_ENABLED,
    TTS_EMOTION_MARKERS,
    TTS_LOUDNORM_ENABLED,
    TTS_LOUDNORM_PARAMS,
    TTS_MAX_CHARS_PER_REQUEST,
    TTS_MAX_SECS_PER_CHAR,
    TTS_MIN_SECS_PER_CHAR,
    TTS_OUTPUT_FORMAT,
    TTS_SAMPLE_RATE,
    TTS_SHORT_TEXT_PADDING,
    TTS_SPEED,
    VOICE_DEFAULT,
    VOICE_PRESETS,
    VOICE_REFERENCE_TEXTS,
)
from ai_worker.tts.normalizer import normalize_for_tts
from ai_worker.tts.alignment import transcribe_tts_quality
from ai_worker.tts.quality import (
    TranscriptQuality,
    assess_audio_with_asr,
    candidate_seed,
    quality_retry_decision,
    should_run_asr_quality_check,
    validate_segment_boundaries,
)

logger = logging.getLogger(__name__)

VOICES_DIR = Path(__file__).parent.parent.parent / "assets" / "voices"
_REF_AUDIO_EXTS = (".wav", ".mp3", ".flac")

# 재시도 정책
_MAX_TTS_RETRIES = 2       # HTTP 5xx / ReadTimeout 재시도
_MAX_QUALITY_RETRIES = 2   # 오디오 길이 검증 실패 시 재생성

# 짧은 텍스트 한국어 패딩 (TTS_SHORT_TEXT_PADDING일 때만; S1+참조에선 보통 불필요)
_MIN_SAFE_TEXT_LEN = 20
_SHORT_TEXT_PREFIX = "다음은 한국어 내용입니다. "

_HTTP_TIMEOUT = httpx.Timeout(
    connect=10.0,
    write=FISH_SPEECH_TIMEOUT,   # 대형 base64 참조 오디오 업로드 대비
    read=FISH_SPEECH_TIMEOUT,
    pool=5.0,
)


@asynccontextmanager
async def _fish_speech_request_lock():
    """Serialize Fish requests without consuming shared ASR executor workers.

    The lock is thread based because ``synthesize`` is also called from the
    renderer's private event-loop thread.  If a caller is cancelled while its
    acquire is queued, the worker still obtains the lock eventually; release it
    in a completion callback so that cancellation cannot permanently wedge TTS.
    """
    loop = asyncio.get_running_loop()
    acquired = False
    acquire_future = loop.run_in_executor(
        _FISH_SPEECH_LOCK_EXECUTOR,
        _FISH_SPEECH_LOCK.acquire,
    )
    try:
        await asyncio.shield(acquire_future)
        acquired = True
        yield
    except BaseException:
        if not acquired:
            def _release_after_cancelled_acquire(
                completed: asyncio.Future[object],
            ) -> None:
                if not completed.cancelled() and completed.exception() is None:
                    _FISH_SPEECH_LOCK.release()

            acquire_future.add_done_callback(_release_after_cancelled_acquire)
        raise
    finally:
        if acquired:
            _FISH_SPEECH_LOCK.release()


# ────────────────────────────────────────────────────────────────
# 워밍업 센티널 — ai_worker 재시작 시 불필요한 재워밍업 방지
# ────────────────────────────────────────────────────────────────
_WARMUP_SENTINEL_MAX_AGE_HOURS = 6
_warmup_done: bool = False


def _get_warmup_sentinel_path() -> Path:
    from config.settings import MEDIA_DIR
    return Path(MEDIA_DIR) / "tmp" / "fish_warmup_state.json"


def _load_warmup_sentinel() -> dict | None:
    p = _get_warmup_sentinel_path()
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _save_warmup_sentinel() -> None:
    p = _get_warmup_sentinel_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps({"warmed_at": time.time(), "url": FISH_SPEECH_URL}),
        encoding="utf-8",
    )
    logger.debug("[warmup] 센티널 저장 완료: %s", p)


# ────────────────────────────────────────────────────────────────
# 참조 음성 해석 + per-voice 파라미터
# ────────────────────────────────────────────────────────────────
def _ref_pairs(folder: Path) -> list[tuple[Path, Path]]:
    """폴더 내 (오디오, .lab) 쌍 목록. .lab 없는 오디오는 제외."""
    pairs: list[tuple[Path, Path]] = []
    if not folder.is_dir():
        return pairs
    for audio in sorted(folder.iterdir()):
        if audio.suffix.lower() in _REF_AUDIO_EXTS:
            lab = audio.with_suffix(".lab")
            if lab.is_file():
                pairs.append((audio, lab))
    return pairs


def _resolve_references(voice_key: str) -> dict:
    """voice_key → /v1/tts 페이로드의 참조 음성 조각을 반환한다.

    우선순위:
      1. 폴더 기반(reference_id): assets/voices/<ref_dir>/ 에 NN.wav+NN.lab 쌍 존재
      2. 레거시 평면 파일: base64 references (단일 샘플)
      3. 폴백: references=[] + 경고 (기본 음색으로 합성됨)
    """
    preset = VOICE_PRESETS.get(voice_key) or VOICE_PRESETS.get(VOICE_DEFAULT, {})
    ref_dir = preset.get("ref_dir")

    # 1. 폴더 기반 클로닝 (reference_id)
    if ref_dir and _ref_pairs(VOICES_DIR / ref_dir):
        return {
            "reference_id": ref_dir,
            "use_memory_cache": FISH_SPEECH_USE_MEMORY_CACHE,
        }

    # 2. 레거시 평면 파일 (voices/<filename>, 하위경로 아님)
    file = preset.get("file")
    if file and "/" not in str(file):
        flat = VOICES_DIR / file
        if flat.is_file():
            ref_text = VOICE_REFERENCE_TEXTS.get(
                voice_key, VOICE_REFERENCE_TEXTS.get(VOICE_DEFAULT, ""),
            )
            audio_b64 = base64.b64encode(flat.read_bytes()).decode()
            return {"references": [{"audio": audio_b64, "text": ref_text}]}

    # 3. 폴백
    logger.warning(
        "참조 음성 없음 — voice=%s (폴더 '%s', 평면파일 '%s' 모두 부재). 기본 음색으로 합성됨. "
        "worker/tools/prepare_voice.py 로 음성을 등록하세요.",
        voice_key, ref_dir, file,
    )
    return {"references": []}


def _voice_params(voice_key: str) -> dict:
    """전역 기본값 위에 voices.json per-voice params를 머지한 생성 파라미터."""
    preset = VOICE_PRESETS.get(voice_key) or VOICE_PRESETS.get(VOICE_DEFAULT, {})
    p = preset.get("params") or {}
    return {
        "temperature": float(p.get("temperature", FISH_SPEECH_TEMPERATURE)),
        "top_p": float(p.get("top_p", FISH_SPEECH_TOP_P)),
        "repetition_penalty": float(p.get("repetition_penalty", FISH_SPEECH_REPETITION_PENALTY)),
        "speed": float(p.get("speed", TTS_SPEED)),
    }


def _base_payload(ref_fragment: dict, params: dict) -> dict:
    """텍스트를 제외한 /v1/tts 공통 페이로드."""
    payload: dict = {
        "format": TTS_OUTPUT_FORMAT,
        "chunk_length": FISH_SPEECH_CHUNK_LENGTH,
        "normalize": FISH_SPEECH_NORMALIZE,
        "temperature": params["temperature"],
        "top_p": params["top_p"],
        "repetition_penalty": params["repetition_penalty"],
        **ref_fragment,
    }
    if FISH_SPEECH_SEED is not None:
        payload["seed"] = FISH_SPEECH_SEED
    return payload


# ────────────────────────────────────────────────────────────────
# 오디오 길이 검증 (WAV 헤더 파싱) + 텍스트 분할
# ────────────────────────────────────────────────────────────────
def _wav_duration(content: bytes) -> float:
    """WAV 바이트에서 재생 길이(초)를 헤더 파싱으로 계산.

    샘플레이트를 하드코딩하지 않고 fmt 청크에서 읽는다 (S1 출력 SR이 44100이 아닐 수 있음).
    파싱 실패 시 44100Hz/16bit/mono 가정으로 폴백.
    """
    try:
        if len(content) < 44 or content[:4] != b"RIFF" or content[8:12] != b"WAVE":
            raise ValueError("not RIFF/WAVE")
        pos = 12
        sample_rate, channels, bits, data_size = 44100, 1, 16, 0
        while pos + 8 <= len(content):
            cid = content[pos:pos + 4]
            csize = int.from_bytes(content[pos + 4:pos + 8], "little")
            if cid == b"fmt " and pos + 24 <= len(content):
                channels = int.from_bytes(content[pos + 10:pos + 12], "little") or 1
                sample_rate = int.from_bytes(content[pos + 12:pos + 16], "little") or 44100
                bits = int.from_bytes(content[pos + 22:pos + 24], "little") or 16
            elif cid == b"data":
                data_size = csize
            pos += 8 + csize + (csize & 1)  # 청크는 워드 정렬
        byte_rate = sample_rate * channels * (bits // 8)
        if byte_rate <= 0:
            raise ValueError("bad byte_rate")
        if data_size <= 0:
            data_size = max(len(content) - 44, 0)
        return data_size / byte_rate
    except Exception:
        return max(len(content) - 44, 0) / (44100 * 2)


def _band_distance(spc: float, char_count: int) -> float:
    """초/자 비율이 정상 범위에서 벗어난 정도. 0이면 정상.

    하한(잘림 감지)은 10자 이상 텍스트에만 적용 (짧은 텍스트는 비율 변동이 큼).
    """
    if spc > TTS_MAX_SECS_PER_CHAR:
        return spc - TTS_MAX_SECS_PER_CHAR
    if char_count >= 10 and spc < TTS_MIN_SECS_PER_CHAR:
        return TTS_MIN_SECS_PER_CHAR - spc
    return 0.0


def _split_at_word_boundaries(text: str, max_chars: int) -> list[str]:
    """Split an overlong unit only between whitespace-delimited words.

    ``max_chars`` is a request-size target, not permission to cut a Korean
    eojeol.  A single exceptionally long word therefore stays intact and may
    exceed the target rather than becoming two malformed TTS inputs.
    """
    words = list(re.finditer(r"\S+", text))
    if not words:
        return []
    chunks: list[str] = []
    current_start: int | None = None
    current_end = 0
    for word in words:
        if current_start is None:
            current_start, current_end = word.start(), word.end()
        elif word.end() - current_start <= max_chars:
            current_end = word.end()
        else:
            chunks.append(text[current_start:current_end].strip())
            current_start, current_end = word.start(), word.end()
    if current_start is not None:
        chunks.append(text[current_start:current_end].strip())
    return chunks


def _split_sentence_units(block: str) -> list[str]:
    """Keep sentence punctuation with its preceding unit for natural prosody."""
    return [
        unit.strip()
        # A boundary without whitespace can be part of one lexical token
        # (for example ``버전1.2.3``).  Splitting there would also rejoin the
        # pieces with spaces below, changing the TTS input.
        for unit in re.split(r'(?<=[.!?…])(?:[ \t]+|$)', block.strip())
        if unit.strip()
    ]


def _split_text(text: str, max_chars: int) -> list[str]:
    """Split TTS input without ever cutting inside a Korean word.

    Boundary priority is sentence punctuation, then the blank-line semantic
    blocks emitted by ``ScriptData.to_narration_text()``, then ordinary
    whitespace.  A request may exceed ``max_chars`` only for one unbreakable
    word; this is preferable to synthesizing a broken Hangul eojeol.
    """
    if len(text) <= max_chars:
        return [text]
    chunks: list[str] = []
    current = ""
    semantic_blocks = [
        block.strip() for block in re.split(r'\n\s*\n+', text) if block.strip()
    ]
    for block_index, block in enumerate(semantic_blocks):
        sentence_units = _split_sentence_units(block)
        for unit_index, sentence in enumerate(sentence_units):
            units = (
                _split_at_word_boundaries(sentence, max_chars)
                if len(sentence) > max_chars
                else [sentence]
            )
            for split_index, unit in enumerate(units):
                semantic_start = block_index > 0 and unit_index == 0 and split_index == 0
                separator = "\n\n" if semantic_start else " "
                if not current:
                    current = unit
                elif len(current) + len(separator) + len(unit) <= max_chars:
                    current = f"{current}{separator}{unit}"
                else:
                    chunks.append(current)
                    current = unit
    if current:
        chunks.append(current)
    return chunks or [text]


# ────────────────────────────────────────────────────────────────
# 오디오 후처리 + 세그먼트 병합
# ────────────────────────────────────────────────────────────────
def _post_process_audio(path: Path, speed: float = TTS_SPEED, trim_prefix_secs: float = 0.0) -> None:
    """FFmpeg 후처리: (선택)패딩 트림 → loudnorm → 배속.

    출력은 항상 44100Hz mono pcm_s16le 로 강제한다. loudnorm 단일 패스는 내부적으로
    192kHz를 출력하므로, 렌더러의 44.1kHz concat(_merge_chunks의 -c copy, anullsrc=r=44100)과
    포맷이 어긋나지 않도록 출력 샘플레이트를 고정해야 한다.

    ffmpeg 미설치 환경은 조용히 건너뜀.
    """
    tmp = path.with_name(path.stem + "_proc.wav")
    filters: list[str] = []
    if trim_prefix_secs > 0:
        filters.append(f"atrim=start={trim_prefix_secs:.3f},asetpts=PTS-STARTPTS")
    # silenceremove 제거: 호흡/짧은 휴지를 "무음"으로 보고 본문을 잘라
    # 가공 노이즈·잘림의 주원인이었음. loudnorm+atempo만 유지.
    if TTS_LOUDNORM_ENABLED:
        filters.append(f"loudnorm={TTS_LOUDNORM_PARAMS}")
    if abs(speed - 1.0) > 1e-3:
        filters.append(f"atempo={speed}")
    af_chain = ",".join(filters)
    try:
        result = subprocess.run(
            [
                "ffmpeg", "-y", "-i", str(path),
                "-af", af_chain,
                "-ar", str(TTS_SAMPLE_RATE), "-ac", "1", "-c:a", "pcm_s16le",
                str(tmp),
            ],
            capture_output=True,
            timeout=60,
        )
        if result.returncode == 0 and tmp.exists() and tmp.stat().st_size > 0:
            tmp.replace(path)
            logger.debug("오디오 후처리 완료 (loudnorm+%.2f배속): %s", speed, path.name)
        else:
            logger.warning(
                "오디오 후처리 실패 (rc=%d): %s",
                result.returncode,
                result.stderr[-200:].decode(errors="replace") if result.stderr else "",
            )
    except FileNotFoundError:
        logger.debug("ffmpeg 미설치 — 오디오 후처리 건너뜀")
    except Exception as exc:
        logger.warning("오디오 후처리 오류: %s", exc)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)


def _concat_wavs(seg_files: list[Path], output_path: Path) -> None:
    """세그먼트 WAV들을 concat demuxer(-c copy)로 병합한다.

    모든 세그먼트는 동일 서버에서 동일 포맷으로 생성되므로 -c copy 안전.
    (후처리 전 단계라 모두 raw S1 출력 포맷으로 동일.)
    """
    concat_file = output_path.with_name(output_path.stem + "_segconcat.txt")
    concat_file.write_text(
        "".join(f"file '{f.resolve()}'\n" for f in seg_files), encoding="utf-8",
    )
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0",
             "-i", str(concat_file), "-c", "copy", str(output_path)],
            capture_output=True, check=True, timeout=120,
        )
    finally:
        concat_file.unlink(missing_ok=True)


# ────────────────────────────────────────────────────────────────
# HTTP 요청 + 세그먼트 합성
# ────────────────────────────────────────────────────────────────
async def _request_one(client: httpx.AsyncClient, payload: dict) -> bytes:
    """단일 /v1/tts 요청 (5xx/ReadTimeout 재시도 포함). 응답 bytes 반환."""
    async with _fish_speech_request_lock():
        for attempt in range(_MAX_TTS_RETRIES + 1):
            try:
                resp = await client.post(f"{FISH_SPEECH_URL}/v1/tts", json=payload)
                resp.raise_for_status()
                return resp.content
            except httpx.HTTPStatusError as e:
                if e.response.status_code >= 500 and attempt < _MAX_TTS_RETRIES:
                    wait = 30 * (attempt + 1)
                    logger.warning(
                        "Fish Speech %d (attempt %d/%d) — %d초 후 재시도",
                        e.response.status_code, attempt + 1, _MAX_TTS_RETRIES + 1, wait,
                    )
                    await asyncio.sleep(wait)
                else:
                    raise
            except httpx.ReadTimeout:
                if attempt < _MAX_TTS_RETRIES:
                    logger.warning(
                        "Fish Speech ReadTimeout (attempt %d/%d) — 즉시 재시도",
                        attempt + 1, _MAX_TTS_RETRIES + 1,
                    )
                else:
                    logger.error("Fish Speech ReadTimeout — 최대 재시도(%d) 초과", _MAX_TTS_RETRIES + 1)
                    raise
    raise RuntimeError("unreachable")


async def _synthesize_segment(
    client: httpx.AsyncClient,
    send_text: str,
    char_count: int,
    base_payload: dict,
    *,
    voice_key: str,
    expected_text: str,
) -> tuple[bytes, float]:
    """품질 검증 + 재생성 포함 단일 세그먼트 합성. (오디오 bytes, 초/자) 반환.

    char_count: 마커·패딩을 제외한 원문 길이 (품질 비율 계산 기준).
    """
    best_audio: bytes | None = None
    best_dist = float("inf")
    best_spc = 0.0
    best_asr_audio: bytes | None = None
    best_asr_spc = 0.0
    best_asr_score = float("-inf")
    for q in range(_MAX_QUALITY_RETRIES + 1):
        seed = candidate_seed(voice_key, send_text, q)
        content = await _request_one(client, {**base_payload, "text": send_text, "seed": seed})
        dur = _wav_duration(content)
        spc = dur / max(char_count, 1)
        dist = _band_distance(spc, char_count)
        if dist != 0.0:
            if dist < best_dist:
                best_dist, best_audio, best_spc = dist, content, spc
            logger.warning(
                "TTS 길이 품질 의심: %.1f초/%.0f자 = %.2f초/자 (범위 %.2f~%.2f) — 재생성 %d/%d",
                dur, char_count, spc, TTS_MIN_SECS_PER_CHAR, TTS_MAX_SECS_PER_CHAR,
                q + 1, _MAX_QUALITY_RETRIES,
            )
            continue

        loop = asyncio.get_running_loop()
        quality = await loop.run_in_executor(
            None,
            _assess_segment_quality,
            content,
            expected_text,
            dur,
        )
        # All duration-valid candidates can still be rejected by ASR.  Preserve
        # the most text-faithful one for an exhausted retry budget instead of
        # accidentally returning the final attempt with a zero timing estimate.
        # Coverage is a secondary tiebreaker because it is intentionally absent
        # for short/unspaced transcripts.
        quality_score = quality.similarity + (quality.word_coverage or 0.0) * 1e-3
        if quality_score > best_asr_score:
            best_asr_audio, best_asr_spc, best_asr_score = content, spc, quality_score
        decision = quality_retry_decision(
            quality,
            voice_key=voice_key,
            text=send_text,
            attempt=q,
            max_retries=_MAX_QUALITY_RETRIES,
        )
        if not decision.retry:
            if quality.requires_retry:
                # The final rejected candidate is not automatically the best
                # one.  Leave the loop so the highest-quality failed ASR
                # candidate recorded above is selected below.
                break
            if quality.status == "inconclusive":
                logger.info("TTS ASR 품질 검사 불확정 — 후보 수용: %s", quality.reason)
            elif quality.status == "skipped":
                logger.debug("TTS ASR 품질 검사 생략: %s", quality.reason)
            return content, spc
        logger.warning(
            "TTS ASR 품질 의심: reason=%s similarity=%.3f missing=%s — 재생성 %d/%d",
            quality.reason,
            quality.similarity,
            ", ".join(quality.missing_fragments) or "—",
            q + 1,
            _MAX_QUALITY_RETRIES,
        )
    if best_asr_audio is not None:
        logger.warning("TTS ASR 품질 검증 최종 실패 — 최적 후보 사용 (%.2f초/자)", best_asr_spc)
        return best_asr_audio, best_asr_spc
    logger.warning("TTS 길이 품질 검증 최종 실패 — 최적 결과 사용 (%.2f초/자)", best_spc)
    return (best_audio if best_audio is not None else content), best_spc


def _assess_segment_quality(
    content: bytes,
    expected_text: str,
    duration_seconds: float,
) -> TranscriptQuality:
    """임시 WAV의 CPU ASR 검사를 worker thread에서 수행하고 반드시 정리한다."""
    if not should_run_asr_quality_check(expected_text, duration_seconds=duration_seconds):
        # 경로가 없어도 assess helper가 ASR skip 결과를 만든다. 이 분기는 아주 짧은
        # 카피에 tempfile I/O와 CPU Whisper 모델 로드를 모두 피한다.
        return assess_audio_with_asr(
            expected_text,
            None,
            lambda _path: transcribe_tts_quality(_path, expected_text),
            duration_seconds=duration_seconds,
        )
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
            temp_file.write(content)
            temp_path = Path(temp_file.name)
        return assess_audio_with_asr(
            expected_text,
            temp_path,
            lambda path: transcribe_tts_quality(path, expected_text),
            duration_seconds=duration_seconds,
        )
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


# ────────────────────────────────────────────────────────────────
# 공개 API
# ────────────────────────────────────────────────────────────────
async def synthesize(
    text: str,
    scene_type: str = "image_text",
    voice_key: str = VOICE_DEFAULT,
    output_path: Path | None = None,
    emotion: str = "",
) -> Path:
    """OpenAudio S1으로 TTS를 생성하고 wav 파일 경로를 반환한다.

    Args:
        text:        읽을 텍스트
        scene_type:  씬 타입 (로깅용)
        voice_key:   VOICE_PRESETS 키
        output_path: 저장 경로 (None이면 /tmp 임시파일)
        emotion:     tts_emotion 키 (예: "sad"). TTS_EMOTION_MARKERS로 마커 주입.

    Returns:
        생성된 wav 파일 경로 (44100Hz mono)

    Raises:
        ValueError:            정규화 후 빈 텍스트
        httpx.HTTPStatusError: Fish Speech 서버 오류 (5xx)
    """
    global _warmup_done
    if not _warmup_done:
        logger.info("synthesize() 첫 호출 — 자동 웜업 실행")
        await _warmup_model()

    normalized = normalize_for_tts(text)
    stripped = normalized.strip().rstrip(".")
    if not stripped:
        logger.warning("TTS 스킵: 정규화 후 빈 텍스트 (원문: '%s')", text[:50])
        raise ValueError(f"TTS 입력 텍스트가 정규화 후 비어있음 (원문: '{text[:50]}')")

    # 감정 마커 (정규화 후 주입)
    marker = ""
    if TTS_EMOTION_ENABLED and emotion:
        marker = TTS_EMOTION_MARKERS.get(emotion, "")

    ref_fragment = _resolve_references(voice_key)
    params = _voice_params(voice_key)
    speed = params["speed"]
    base_payload = _base_payload(ref_fragment, params)

    segments = _split_text(normalized, TTS_MAX_CHARS_PER_REQUEST)
    boundary_report = validate_segment_boundaries(segments, source_text=normalized)
    if not boundary_report.valid:
        contexts = [
            f"{issue.left_context}|{issue.right_context}"
            for issue in boundary_report.unsafe_boundaries
        ]
        raise ValueError(
            "TTS 세그먼트가 한국어 어절 중간에서 분할됨: " + ", ".join(contexts)
        )
    if boundary_report.indeterminate_boundaries:
        raise ValueError(
            "TTS 세그먼트 경계를 원문에 대응할 수 없음: "
            f"{boundary_report.indeterminate_boundaries}개"
        )

    # 짧은 텍스트 패딩 (게이트, 단일 세그먼트일 때만)
    pad_prefix = ""
    if TTS_SHORT_TEXT_PADDING and len(segments) == 1 and len(normalized) < _MIN_SAFE_TEXT_LEN:
        pad_prefix = _SHORT_TEXT_PREFIX
        logger.info("TTS 짧은 텍스트 패딩 적용: voice=%s '%s'", voice_key, normalized[:30])

    if output_path is None:
        output_path = Path(
            f"/tmp/tts_{hashlib.md5(normalized.encode()).hexdigest()[:16]}.{TTS_OUTPUT_FORMAT}"
        )

    seg_files: list[Path] = []
    pad_trim_secs = 0.0
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        for i, seg in enumerate(segments):
            send_text = f"{marker} {seg}".strip() if marker else seg
            if pad_prefix:
                send_text = pad_prefix + send_text
            content, spc = await _synthesize_segment(
                client,
                send_text,
                len(seg),
                base_payload,
                voice_key=voice_key,
                expected_text=seg,
            )
            if pad_prefix:
                pad_trim_secs = len(pad_prefix) * spc
            if len(segments) == 1:
                output_path.write_bytes(content)
                seg_files = [output_path]
            else:
                seg_path = output_path.with_name(f"{output_path.stem}_seg{i:02d}.wav")
                seg_path.write_bytes(content)
                seg_files.append(seg_path)

    if len(seg_files) > 1:
        _concat_wavs(seg_files, output_path)
        for f in seg_files:
            f.unlink(missing_ok=True)

    _post_process_audio(output_path, speed=speed, trim_prefix_secs=pad_trim_secs)

    logger.info(
        "TTS 생성 완료: scene=%s voice=%s emotion=%s text=%d자 seg=%d → %s (%dKB)",
        scene_type, voice_key, emotion or "—", len(text), len(segments),
        output_path.name, output_path.stat().st_size // 1024,
    )
    return output_path


async def _warmup_model() -> None:
    """OpenAudio S1 모델 + 음성 클로닝 웜업.

    서버는 첫 요청에서 모델을 lazy-load 하고 reference_id 인코딩을 메모리 캐시한다.
    실제 합성 전에 무참조 1회 + 음성별 1회(reference_id 프라이밍) 요청을 보내
    첫 합성의 garbling/지연을 방지한다.

    센티널(6시간) 유효 시 1회 프로브로 풀 웜업을 건너뛴다.
    """
    global _warmup_done

    sentinel = _load_warmup_sentinel()
    sentinel_valid = False
    if sentinel is not None:
        age_h = (time.time() - sentinel.get("warmed_at", 0)) / 3600.0
        if age_h <= _WARMUP_SENTINEL_MAX_AGE_HOURS and sentinel.get("url") == FISH_SPEECH_URL:
            sentinel_valid = True

    default_params = _voice_params(VOICE_DEFAULT)
    default_base = _base_payload(_resolve_references(VOICE_DEFAULT), default_params)

    async with _fish_speech_request_lock():
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            # 센티널 유효: 저비용 프로브 1회
            if sentinel_valid:
                try:
                    probe = await client.post(
                        f"{FISH_SPEECH_URL}/v1/tts",
                        json={**default_base, "text": "안녕하세요."},
                    )
                    if probe.status_code < 400:
                        logger.info(
                            "Fish Speech 워밍업 스킵 (캐시 유효, %.1fh 전)",
                            (time.time() - sentinel.get("warmed_at", 0)) / 3600.0,
                        )
                        _warmup_done = True
                        return
                    logger.warning("Fish Speech 프로브 응답 %d — 풀 웜업", probe.status_code)
                except Exception as exc:
                    logger.warning("Fish Speech 프로브 실패 (%s) — 풀 웜업", exc)

            # 풀 웜업
            try:
                # 1) 모델 로드 트리거 (무참조)
                await client.post(
                    f"{FISH_SPEECH_URL}/v1/tts",
                    json={**default_base, "references": [], "text": "안녕하세요. 오늘도 좋은 하루 되세요."},
                )
                # 2) 음성별 reference_id 프라이밍 (참조 가능한 것만)
                warmed = 0
                for vk in VOICE_PRESETS:
                    frag = _resolve_references(vk)
                    if "reference_id" not in frag and not frag.get("references"):
                        continue  # 참조 없는 음성은 스킵 (기본 음색 중복 호출 방지)
                    payload = {
                        **_base_payload(frag, _voice_params(vk)),
                        "text": "안녕하세요, 한국어 테스트 문장입니다.",
                    }
                    try:
                        await client.post(f"{FISH_SPEECH_URL}/v1/tts", json=payload)
                        warmed += 1
                    except Exception as exc:
                        logger.warning("음성 웜업 실패 (%s): %s", vk, exc)
                logger.info("Fish Speech 웜업 완료 (무참조 1 + 음성 %d개)", warmed)
                _warmup_done = True
                _save_warmup_sentinel()
            except Exception as exc:
                logger.warning("Fish Speech 웜업 실패 (무시): %s", exc)


async def wait_for_fish_speech(retries: int = 10, delay: float = 5.0) -> bool:
    """Fish Speech 서버 기동 대기 (컨테이너 시작 직후 호출).

    HTTP 응답(상태코드 무관)을 받으면 서버가 떴다고 보고 웜업까지 완료한다.
    ConnectError만 '아직 기동 전'으로 간주해 재시도한다.

    Returns:
        True if 서버 준비 + 웜업 완료, False if 최종 실패
    """
    async with httpx.AsyncClient(timeout=5) as client:
        for i in range(retries):
            try:
                await client.get(f"{FISH_SPEECH_URL}/")
                logger.info("Fish Speech 서버 준비 완료 (%s)", FISH_SPEECH_URL)
                await _warmup_model()
                return True
            except httpx.ConnectError:
                logger.warning("Fish Speech 대기 중 (%d/%d) — %s", i + 1, retries, FISH_SPEECH_URL)
            except Exception as exc:
                # 연결은 됐으나 다른 오류 → 서버는 떠 있으므로 웜업 시도
                logger.info("Fish Speech 응답 확인 (%s) — 웜업 진행", exc)
                await _warmup_model()
                return True
            await asyncio.sleep(delay)
    logger.error("Fish Speech 서버 연결 실패: %s", FISH_SPEECH_URL)
    return False
