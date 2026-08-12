"""ai_worker/renderer/_tts.py — TTS 청크 생성·병합 로직 (internal)"""

import logging
import re
import subprocess
import wave
from pathlib import Path

logger = logging.getLogger(__name__)

_INTRO_PAUSE_SEC: float = 0.0  # 정렬된 통합 낭독에서는 별도 휴지를 삽입하지 않는다.
_LEADING_SILENCE_DBFS: float = -45.0
_SILENCE_SAMPLE_THRESHOLD: int = round(32768 * 10 ** (_LEADING_SILENCE_DBFS / 20))
_SPEECH_DEBOUNCE_FRAMES: int = 3


def _is_narrator_sentence(sent: dict) -> bool:
    """통합 낭독 wav에 포함된 구간 (hook/body). closer·댓글·채팅은 제외."""
    if not sent:
        return False
    bt = sent.get("block_type") or ""
    if bt in ("comment", "chat"):
        return False
    sec = sent.get("section") or ""
    if sec in ("comment", "closer"):
        return False
    return sec in ("hook", "body")


def _split_narration_at_aligned_starts(
    src: Path,
    starts: list[float],
    out_paths: list[Path],
    *,
    initial_lead_sec: float,
) -> list[float]:
    """실제 발화 경계에서만 통합 낭독 wav를 분할한다.

    문자 수 비율 추정이나 fade는 쓰지 않는다. 연속된 내레이터 프레임은 원본의
    샘플 순서를 그대로 되이어 놓으므로, 재생 시 통합 wav의 억양과 호흡이 유지된다.
    첫 조각에만 텍스트 선행 표시를 위한 무음 리드를 더한다.
    """
    if len(starts) != len(out_paths):
        raise ValueError("starts/out_paths length mismatch")
    if not starts:
        return []
    total_dur = _get_audio_duration(src)
    if starts[0] < 0 or any(b <= a for a, b in zip(starts, starts[1:])):
        raise ValueError(f"invalid aligned narration starts: {starts}")
    if starts[-1] >= total_dur:
        raise ValueError(f"last narration start {starts[-1]:.3f} >= audio {total_dur:.3f}")

    durations: list[float] = []
    for i, out_p in enumerate(out_paths):
        start = 0.0 if i == 0 else starts[i]
        end = starts[i + 1] if i + 1 < len(starts) else total_dur
        seg = max(end - start, 0.001)
        # Never fade/crossfade the narrator. Boundaries are ASR-aligned to the
        # next line's first word, not estimated from character counts.
        af = f"atrim=start={start:.6f}:end={end:.6f},asetpts=PTS-STARTPTS"
        if i == 0 and initial_lead_sec > 0:
            delay_ms = round(initial_lead_sec * 1000)
            af += f",adelay={delay_ms}|{delay_ms}"
        result = subprocess.run(
            [
                "ffmpeg", "-y", "-i", str(src),
                "-af", af,
                "-ar", "44100", "-ac", "1", "-c:a", "pcm_s16le",
                str(out_p),
            ],
            capture_output=True, timeout=60,
        )
        if result.returncode != 0 or not out_p.exists() or out_p.stat().st_size < 64:
            logger.warning(
                "[tts] aligned narration split failed i=%d — silence fallback (%s)",
                i, (result.stderr[-200:] if result.stderr else b"").decode(errors="replace"),
            )
            subprocess.run(
                [
                    "ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
                    "-t", f"{seg + (initial_lead_sec if i == 0 else 0):.4f}",
                    "-c:a", "pcm_s16le", str(out_p),
                ],
                capture_output=True, check=True, timeout=10,
            )
        actual = _get_audio_duration(out_p) if out_p.exists() else seg
        durations.append(actual)
    logger.info(
        "[tts] narration aligned split: src=%.3fs → %d parts (starts=%s)",
        total_dur, len(durations), [round(start, 3) for start in starts],
    )
    return durations


def _append_silence(wav_path: Path, seconds: float) -> float:
    """Append an intentional pause without touching the existing waveform."""
    if seconds <= 0:
        return _get_audio_duration(wav_path)
    padded = wav_path.with_suffix(".pause.wav")
    try:
        result = subprocess.run(
            [
                "ffmpeg", "-y", "-i", str(wav_path),
                "-af", f"apad=pad_dur={seconds:.3f}",
                "-c:a", "pcm_s16le", str(padded),
            ],
            capture_output=True, timeout=30,
        )
        if result.returncode != 0 or not padded.exists():
            raise RuntimeError("ffmpeg pause append failed")
        padded.replace(wav_path)
        return _get_audio_duration(wav_path)
    finally:
        padded.unlink(missing_ok=True)


def _prepend_silence(wav_path: Path, seconds: float) -> float:
    """Delay a newly-generated first utterance without altering its waveform."""
    if seconds <= 0:
        return _get_audio_duration(wav_path)
    delayed = wav_path.with_suffix(".lead.wav")
    delay_ms = round(seconds * 1000)
    try:
        result = subprocess.run(
            [
                "ffmpeg", "-y", "-i", str(wav_path),
                "-af", f"adelay={delay_ms}|{delay_ms}",
                "-c:a", "pcm_s16le", str(delayed),
            ],
            capture_output=True, timeout=30,
        )
        if result.returncode != 0 or not delayed.exists():
            raise RuntimeError("ffmpeg lead delay failed")
        delayed.replace(wav_path)
        return _get_audio_duration(wav_path)
    finally:
        delayed.unlink(missing_ok=True)


def _measure_leading_silence(wav_path: Path) -> float:
    """Return leading digital silence of a mono/stereo PCM s16 WAV in seconds.

    TTS output and its disk cache are normalized to PCM s16le.  A -45 dBFS
    threshold treats measured pre-speech noise as lead silence; three
    consecutive over-threshold frames reject isolated clicks. Use a tiny
    stdlib-only scan instead of broad ``silenceremove``: the existing waveform
    is never trimmed, and a decode failure merely causes a conservative full
    lead pad later.
    """
    try:
        with wave.open(str(wav_path), "rb") as wav_file:
            if wav_file.getsampwidth() != 2 or wav_file.getcomptype() != "NONE":
                raise ValueError("expected PCM s16 WAV")
            channels = wav_file.getnchannels()
            sample_rate = wav_file.getframerate()
            if channels < 1 or sample_rate < 1:
                raise ValueError("invalid WAV format")

            frames_read = 0
            candidate_start = 0
            consecutive_loud_frames = 0
            while True:
                raw = wav_file.readframes(4096)
                if not raw:
                    return frames_read / sample_rate
                sample_count = len(raw) // 2
                samples = memoryview(raw).cast("h")
                frame_count = sample_count // channels
                for frame_idx in range(frame_count):
                    start = frame_idx * channels
                    if any(abs(samples[start + channel]) >= _SILENCE_SAMPLE_THRESHOLD for channel in range(channels)):
                        if consecutive_loud_frames == 0:
                            candidate_start = frames_read
                        consecutive_loud_frames += 1
                        if consecutive_loud_frames >= _SPEECH_DEBOUNCE_FRAMES:
                            return candidate_start / sample_rate
                    else:
                        consecutive_loud_frames = 0
                    frames_read += 1
    except Exception:
        logger.warning("[tts] leading silence 측정 실패: %s", wav_path.name, exc_info=True)
        return 0.0


def _ensure_initial_text_lead(wav_path: Path, target_lead_sec: float) -> float:
    """Pad only the missing PCM lead before the first visible utterance.

    Fish WAVs can already contain natural pre-speech room tone.  Measuring the
    rendered PCM chunk (rather than assuming an empty container) keeps the
    text-to-first-syllable interval at the requested target without trimming
    that natural lead.
    """
    existing_lead = _measure_leading_silence(wav_path)
    lead_padding = max(target_lead_sec - existing_lead, 0.0)
    duration = (
        _prepend_silence(wav_path, lead_padding)
        if lead_padding > 0
        else _get_audio_duration(wav_path)
    )
    logger.info(
        "[layout] initial text lead existing=%.3fs padding=%.3fs target=%.3fs (%s)",
        existing_lead, lead_padding, target_lead_sec, wav_path.name,
    )
    return duration


def _apply_outro_timing(plan: list[dict], durations: list[float], output_dir: Path) -> list[float]:
    """Apply the fixed pause/lead-tail contract around the closing utterance."""
    outro_idx = next(
        (i for i, entry in enumerate(plan) if entry.get("type") == "outro"),
        None,
    )
    if outro_idx is None or outro_idx == 0:
        return durations

    from config.settings import (
        TTS_OUTRO_PRE_PAUSE_SEC,
        TTS_OUTRO_TAIL_SEC,
        TTS_OUTRO_TEXT_LEAD_SEC,
    )

    previous_path = output_dir / f"chunk_{outro_idx - 1:03d}.wav"
    if previous_path.exists() and durations[outro_idx - 1] > 0:
        durations[outro_idx - 1] = _append_silence(previous_path, TTS_OUTRO_PRE_PAUSE_SEC)
        logger.info(
            "[layout] outro 전 %.2fs 휴지 삽입 (frame=%d)",
            TTS_OUTRO_PRE_PAUSE_SEC, outro_idx - 1,
        )
    outro_path = output_dir / f"chunk_{outro_idx:03d}.wav"
    if outro_path.exists() and durations[outro_idx] > 0:
        existing_lead = _measure_leading_silence(outro_path)
        lead_padding = max(TTS_OUTRO_TEXT_LEAD_SEC - existing_lead, 0.0)
        if lead_padding > 0:
            durations[outro_idx] = _prepend_silence(outro_path, lead_padding)
        logger.info(
            "[layout] outro lead existing=%.3fs padding=%.3fs target=%.3fs",
            existing_lead, lead_padding, TTS_OUTRO_TEXT_LEAD_SEC,
        )
        durations[outro_idx] = _append_silence(outro_path, TTS_OUTRO_TAIL_SEC)
        logger.info(
            "[layout] outro 후 %.2fs tail 삽입 (frame=%d)",
            TTS_OUTRO_TAIL_SEC, outro_idx,
        )
    return durations




def _get_audio_duration(path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(result.stdout.strip())



def _outro_cache_path(voice_key: str, text: str) -> Path:
    """고정 클로징 멘트 캐시 경로 (voice+text)."""
    import hashlib
    from config.settings import MEDIA_DIR
    digest = hashlib.sha1((text or "").strip().encode("utf-8")).hexdigest()[:12]
    safe_voice = re.sub(r"[^a-zA-Z0-9_-]+", "_", (voice_key or "default").strip()) or "default"
    cache_dir = Path(MEDIA_DIR) / "audio" / "outro_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / f"{safe_voice}_{digest}.wav"


def _loudnorm_inplace(wav_path: Path) -> None:
    """짧은 클립(댓글/outro) 음량을 본문과 같은 타깃으로 맞춘다.

    단일 패스 loudnorm은 1~2초 클립에서 I 측정이 붕괴해 과소/과대 증폭이
    난다. 2-pass 후에도 I가 타깃 밴드 밖이면 **양방향** volume gain
    (키우기·줄이기) + true-peak 리미터로 수렴시킨다.
    """
    import json as _json
    try:
        from config.settings import TTS_LOUDNORM_ENABLED, TTS_LOUDNORM_PARAMS
    except Exception:
        TTS_LOUDNORM_ENABLED, TTS_LOUDNORM_PARAMS = True, "I=-16:TP=-1.5:LRA=11"
    if not TTS_LOUDNORM_ENABLED or not wav_path.exists():
        return

    target_i, target_tp, target_lra = -16.0, -1.5, 11.0
    for part in (TTS_LOUDNORM_PARAMS or "").split(":"):
        if part.startswith("I="):
            try:
                target_i = float(part[2:])
            except ValueError:
                pass
        elif part.startswith("TP="):
            try:
                target_tp = float(part[3:])
            except ValueError:
                pass
        elif part.startswith("LRA="):
            try:
                target_lra = float(part[4:])
            except ValueError:
                pass

    # Accept band around target (LUFS). Too-loud first comments were accepted
    # under the old "out_i > target_i - 6" check (e.g. -10 still OK).
    i_lo, i_hi = target_i - 3.0, target_i + 2.0

    def _parse_loudnorm_json(stderr: str) -> dict:
        jstart = (stderr or "").rfind("{")
        jend = (stderr or "").rfind("}")
        if jstart < 0 or jend <= jstart:
            return {}
        try:
            return _json.loads(stderr[jstart:jend + 1])
        except Exception:
            return {}

    def _measure_i(path: Path) -> float | None:
        check = subprocess.run(
            [
                "ffmpeg", "-y", "-i", str(path),
                "-af", f"loudnorm=I={target_i}:TP={target_tp}:LRA={target_lra}:print_format=json",
                "-f", "null", "-",
            ],
            capture_output=True, text=True, timeout=60,
        )
        raw = _parse_loudnorm_json(check.stderr or "").get("input_i")
        if raw is None:
            return None
        try:
            val = float(raw)
        except (TypeError, ValueError):
            return None
        # -inf / absurd short-clip collapses
        if val < -70.0 or val > 0.0:
            return None
        return val

    def _measure_peak_db(path: Path) -> float | None:
        vd = subprocess.run(
            ["ffmpeg", "-y", "-i", str(path), "-af", "volumedetect", "-f", "null", "-"],
            capture_output=True, text=True, timeout=30,
        )
        for line in (vd.stderr or "").splitlines():
            if "max_volume:" in line:
                try:
                    return float(line.split("max_volume:")[1].strip().split()[0])
                except Exception:
                    return None
        return None

    def _apply_af(path: Path, af: str) -> bool:
        tmp = path.with_suffix(".ln.wav")
        try:
            result = subprocess.run(
                [
                    "ffmpeg", "-y", "-i", str(path),
                    "-af", af,
                    "-ar", "44100", "-ac", "1", "-c:a", "pcm_s16le", str(tmp),
                ],
                capture_output=True, text=True, timeout=60,
            )
            if result.returncode == 0 and tmp.exists() and tmp.stat().st_size > 64:
                tmp.replace(path)
                return True
        finally:
            tmp.unlink(missing_ok=True)
        return False

    def _gain_toward_target(path: Path, measured_i: float | None) -> bool:
        """Bidirectional LUFS gain + peak ceiling. Returns True if applied."""
        gain = None
        if measured_i is not None:
            gain = target_i - measured_i
        else:
            peak = _measure_peak_db(path)
            if peak is None:
                return False
            # Peak-only fallback: aim true peak ≈ target_tp - 0.5
            gain = (target_tp - 0.5) - peak
        # Allow cut as well as boost (was max(0) — left loud clips loud)
        gain = max(-18.0, min(18.0, gain))
        if abs(gain) < 0.4:
            # Still enforce peak ceiling if hot
            peak = _measure_peak_db(path)
            if peak is not None and peak > target_tp:
                cut = target_tp - peak
                if abs(cut) >= 0.3:
                    gain = cut
                else:
                    return False
            else:
                return False
        # alimiter level ≈ linear for target_tp (-1.5 dBTP ≈ 0.84)
        limit = max(0.5, min(0.99, 10 ** (target_tp / 20.0)))
        af = f"volume={gain:.2f}dB,alimiter=limit={limit:.3f}:level=disabled"
        ok = _apply_af(path, af)
        if ok:
            logger.info(
                "[tts] I-gain %+.1fdB (+peak limit) applied to %s (from I≈%s)",
                gain, path.name, f"{measured_i:.1f}" if measured_i is not None else "?",
            )
        return ok

    try:
        # Pass 1 — measure for linear loudnorm
        measure = subprocess.run(
            [
                "ffmpeg", "-y", "-i", str(wav_path),
                "-af", f"loudnorm=I={target_i}:TP={target_tp}:LRA={target_lra}:print_format=json",
                "-f", "null", "-",
            ],
            capture_output=True, text=True, timeout=60,
        )
        measured = _parse_loudnorm_json(measure.stderr or "")
        mi = measured.get("input_i")
        mtp = measured.get("input_tp")
        mlra = measured.get("input_lra")
        mth = measured.get("input_thresh")

        if mi is not None and mtp is not None and mth is not None:
            af = (
                f"loudnorm=I={target_i}:TP={target_tp}:LRA={target_lra}"
                f":measured_I={mi}:measured_TP={mtp}"
                f":measured_LRA={mlra if mlra is not None else 0}"
                f":measured_thresh={mth}:linear=true:print_format=summary"
            )
            tmp = wav_path.with_suffix(".ln.wav")
            result = subprocess.run(
                [
                    "ffmpeg", "-y", "-i", str(wav_path),
                    "-af", af,
                    "-ar", "44100", "-ac", "1", "-c:a", "pcm_s16le", str(tmp),
                ],
                capture_output=True, text=True, timeout=60,
            )
            if result.returncode == 0 and tmp.exists() and tmp.stat().st_size > 64:
                out_i = _measure_i(tmp)
                if out_i is not None and i_lo <= out_i <= i_hi:
                    tmp.replace(wav_path)
                    peak = _measure_peak_db(wav_path)
                    if peak is not None and peak > target_tp + 0.3:
                        _gain_toward_target(wav_path, out_i)
                    logger.info("[tts] 2-pass loudnorm ok %s → I≈%.1f", wav_path.name, out_i)
                    return
                logger.warning(
                    "[tts] 2-pass loudnorm off-target (I≈%s, want %.1f..%.1f) — gain fallback %s",
                    out_i, i_lo, i_hi, wav_path.name,
                )
                # Prefer the 2-pass output as the gain baseline when measurable;
                # otherwise discard and gain from the original file.
                if out_i is not None:
                    tmp.replace(wav_path)
                    if _gain_toward_target(wav_path, out_i):
                        return
                else:
                    tmp.unlink(missing_ok=True)
                    fallback_i = None
                    try:
                        if mi is not None:
                            fallback_i = float(mi)
                            if fallback_i < -70.0 or fallback_i > 0.0:
                                fallback_i = None
                    except (TypeError, ValueError):
                        fallback_i = None
                    if _gain_toward_target(wav_path, fallback_i):
                        return
            else:
                tmp.unlink(missing_ok=True)

        # No usable 2-pass path — gain from original measure / peak
        src_i = None
        try:
            if mi is not None:
                src_i = float(mi)
                if src_i < -70.0 or src_i > 0.0:
                    src_i = None
        except (TypeError, ValueError):
            src_i = None
        if src_i is None:
            src_i = _measure_i(wav_path)
        _gain_toward_target(wav_path, src_i)
    except Exception:
        logger.warning("[tts] loudnorm failed for %s", wav_path.name, exc_info=True)
        wav_path.with_suffix(".ln.wav").unlink(missing_ok=True)



def _unpack_line(item) -> tuple[str, str | None]:
    """text_lines 요소에서 (text, audio_path)를 추출한다.

    content_processor Phase 5 이후 text_lines 요소가
    str → {"text": str, "audio": str|None} dict로 교체되므로 양쪽 형식 모두 처리.
    """
    if isinstance(item, dict):
        return item.get("text", ""), item.get("audio")
    return str(item), None


async def _tts_chunk_async(
    text: str,
    idx: int,
    output_dir: Path,
    scene_type: str = "image_text",
    pre_audio: str | None = None,
    voice_key: str = "default",
    emotion: str = "",
) -> float:
    """문장 TTS 생성. pre_audio가 유효하면 재사용, 없으면 Fish Speech 호출.

    outro(클로징)는 voice+text 키로 디스크 캐시해 매번 같은 음량·톤을 재사용한다.
    """
    import asyncio
    import shutil
    from ai_worker.tts.fish_client import synthesize as fish_synthesize

    out_path = output_dir / f"chunk_{idx:03d}.wav"
    if not text or not text.strip():
        return 0.0

    # 사전 생성된 오디오 재사용
    if pre_audio:
        pre_path = Path(pre_audio)
        if pre_path.exists() and pre_path.stat().st_size > 0:
            shutil.copy2(pre_path, out_path)
            logger.debug("[layout] TTS 재사용: 프레임=%d %s", idx, pre_path.name)
            return _get_audio_duration(out_path)

    # 고정 클로징 멘트 캐시
    cache_path = None
    if scene_type == "outro":
        cache_path = _outro_cache_path(voice_key, text)
        if cache_path.exists() and cache_path.stat().st_size > 1024:
            shutil.copy2(cache_path, out_path)
            _loudnorm_inplace(out_path)  # 구캐시(-34 LUFS)도 재생 시 교정
            # 교정본으로 캐시 갱신
            try:
                shutil.copy2(out_path, cache_path)
            except Exception:
                pass
            logger.info("[layout] outro TTS 캐시 히트(+loudnorm): %s", cache_path.name)
            return _get_audio_duration(out_path)

    # Fish Speech 신규 생성 (Phase 5 실패 시 폴백 경로)
    for attempt in range(2):
        try:
            await fish_synthesize(
                text=text, scene_type=scene_type, voice_key=voice_key,
                output_path=out_path, emotion=emotion,
            )
            break
        except Exception:
            if attempt == 0:
                logger.warning("[layout] TTS 청크 %d 실패 — 5초 후 재시도", idx, exc_info=True)
                await asyncio.sleep(5.0)
            else:
                logger.error("[layout] TTS 청크 %d 최종 실패", idx)
                return 0.0

    if not out_path.exists() or out_path.stat().st_size == 0:
        return 0.0

    if scene_type == "outro" and cache_path is not None:
        # 캐시 전 loudnorm — 재사용 시에도 본문과 비슷한 음량 유지
        _loudnorm_inplace(out_path)
        try:
            shutil.copy2(out_path, cache_path)
            logger.info("[layout] outro TTS 캐시 저장: %s", cache_path.name)
        except Exception:
            logger.warning("[layout] outro 캐시 저장 실패", exc_info=True)

    return _get_audio_duration(out_path)


async def _generate_tts_chunks(
    plan: list[dict],
    sentences: list[dict],
    output_dir: Path,
    voice: str,
    rate: str,
    outro_duration: float = 1.5,
    narration_audio: Path | None = None,
) -> list[float]:
    """plan 순서로 TTS를 생성하고 각 프레임의 지속 시간 목록을 반환한다.

    narration_audio가 있으면 hook/body 구간은 통합 낭독 wav를 실제 발화 시각으로
    정렬해 재사용하고, closer·댓글·채팅만 개별 합성한다.
    """
    durations: list[float] = [0.0] * len(plan)
    narrator_frames: list[int] = []
    narrator_texts: list[str] = []

    use_narration = bool(
        narration_audio is not None
        and Path(narration_audio).exists()
        and Path(narration_audio).stat().st_size > 1024
    )
    if use_narration:
        for frame_idx, entry in enumerate(plan):
            sent_idx = entry.get("sent_idx")
            if sent_idx is None or sent_idx >= len(sentences):
                continue
            sent = sentences[sent_idx]
            if _is_narrator_sentence(sent) and (sent.get("text") or "").strip():
                narrator_frames.append(frame_idx)
                narrator_texts.append(sent["text"])
        if narrator_frames:
            out_paths = [output_dir / f"chunk_{i:03d}.wav" for i in narrator_frames]
            try:
                from ai_worker.tts.alignment import align_narration_lines
                from config.settings import TTS_TEXT_LEAD_SEC

                aligned = align_narration_lines(Path(narration_audio), narrator_texts)
                if aligned is None:
                    raise RuntimeError("narration alignment unavailable")
                starts, confidence = aligned
                part_durs = _split_narration_at_aligned_starts(
                    Path(narration_audio), starts, out_paths,
                    initial_lead_sec=0.0,
                )
                # Alignment timestamps can begin at 0 even when Fish TTS has
                # native PCM lead.  Measure the actual first rendered chunk;
                # using ``starts[0]`` here used to prepend 150 ms on top of
                # that native lead (#453 measured 267.596 ms total).
                part_durs[0] = _ensure_initial_text_lead(
                    out_paths[0], TTS_TEXT_LEAD_SEC,
                )
                for fi, dur in zip(narrator_frames, part_durs):
                    durations[fi] = dur
                logger.info(
                    "[layout] narration wav 정렬 재사용: %d frames confidence=%.3f from %s",
                    len(narrator_frames), confidence, Path(narration_audio).name,
                )
            except Exception:
                logger.warning(
                    "[layout] narration alignment 실패 — 장면별 TTS 폴백",
                    exc_info=True,
                )
                use_narration = False
                narrator_frames = []
        else:
            use_narration = False

    narrator_set = set(narrator_frames) if use_narration else set()

    for frame_idx, entry in enumerate(plan):
        if frame_idx in narrator_set:
            # already filled from narration wav
            scene_type = entry.get("type", "image_text")
            dur = durations[frame_idx]
            if scene_type == "intro" and dur > 0 and _INTRO_PAUSE_SEC > 0:
                chunk_path = output_dir / f"chunk_{frame_idx:03d}.wav"
                tmp_pad = chunk_path.with_suffix(".padded.wav")
                pad_result = subprocess.run(
                    [
                        "ffmpeg", "-y", "-i", str(chunk_path),
                        "-af", f"apad=pad_dur={_INTRO_PAUSE_SEC}",
                        "-c:a", "pcm_s16le", str(tmp_pad),
                    ],
                    capture_output=True, timeout=30,
                )
                if pad_result.returncode == 0 and tmp_pad.exists() and tmp_pad.stat().st_size > 0:
                    tmp_pad.replace(chunk_path)
                    dur += _INTRO_PAUSE_SEC
                    durations[frame_idx] = dur
            logger.debug("[layout] TTS 프레임 %d: %.2fs (narration)", frame_idx, dur)
            continue

        sent_idx = entry.get("sent_idx")
        if sent_idx is not None and sent_idx < len(sentences):
            sent = sentences[sent_idx]
            text = sent["text"]
            pre_audio = sent.get("audio")
            scene_type = entry.get("type", "image_text")
            chunk_voice = (sent.get("voice_override") or voice or "default")
            chunk_emotion = sent.get("tts_emotion", "")
            dur = await _tts_chunk_async(
                text, frame_idx, output_dir, scene_type, pre_audio, chunk_voice, chunk_emotion,
            )
            chunk_path = output_dir / f"chunk_{frame_idx:03d}.wav"
            if dur > 0 and chunk_path.exists():
                # 댓글/채팅: pre_audio(캐시)여도 보이스별 원음량 편차가 커서
                # 항상 양방향 loudnorm으로 본문 I=-16 밴드에 맞춘다.
                if scene_type in ("comments", "chat"):
                    _loudnorm_inplace(chunk_path)
                dur = _get_audio_duration(chunk_path)

            if scene_type == "intro" and dur > 0 and _INTRO_PAUSE_SEC > 0:
                chunk_path = output_dir / f"chunk_{frame_idx:03d}.wav"
                tmp_pad = chunk_path.with_suffix(".padded.wav")
                pad_result = subprocess.run(
                    [
                        "ffmpeg", "-y", "-i", str(chunk_path),
                        "-af", f"apad=pad_dur={_INTRO_PAUSE_SEC}",
                        "-c:a", "pcm_s16le", str(tmp_pad),
                    ],
                    capture_output=True, timeout=30,
                )
                if pad_result.returncode == 0 and tmp_pad.exists() and tmp_pad.stat().st_size > 0:
                    tmp_pad.replace(chunk_path)
                    dur += _INTRO_PAUSE_SEC
                    logger.debug(
                        "[layout] intro TTS 뒤 %.1f초 숨고르기 삽입 (프레임=%d)", _INTRO_PAUSE_SEC, frame_idx
                    )
        else:
            out_path = output_dir / f"chunk_{frame_idx:03d}.wav"
            dwell = float(entry.get("dwell_sec", outro_duration))
            subprocess.run(
                ["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
                 "-t", str(dwell), "-c:a", "pcm_s16le", str(out_path)],
                capture_output=True, check=True, timeout=10,
            )
            dur = dwell
        durations[frame_idx] = dur
        logger.debug("[layout] TTS 프레임 %d: %.2fs", frame_idx, dur)

    # The first visible line is already on-screen at t=0.  When alignment
    # falls back to per-line synthesis, apply the same measured 150 ms lead
    # contract; do not stack it on native Fish pre-speech silence.
    first_audio_idx = next((i for i, dur in enumerate(durations) if dur > 0), None)
    if first_audio_idx is not None and first_audio_idx not in narrator_set:
        from config.settings import TTS_TEXT_LEAD_SEC

        first_path = output_dir / f"chunk_{first_audio_idx:03d}.wav"
        if first_path.exists():
            durations[first_audio_idx] = _ensure_initial_text_lead(
                first_path, TTS_TEXT_LEAD_SEC,
            )

    # The closer is deliberately separated from the final comment/chat by a
    # short pause. This changes only the timeline; existing waveforms remain
    # intact and the closer speech itself is not slowed or faded.
    return _apply_outro_timing(plan, durations, output_dir)



def _merge_chunks(
    chunk_paths: list[Path],
    output_path: Path,
    *,
    skip_global_loudnorm: bool = False,
) -> None:
    """Concat TTS chunks then apply global loudnorm so scene volumes match.

    skip_global_loudnorm=True: 통합 낭독 + 미리 loudnorm된 댓글/outro를 이어붙일 때
    전역 loudnorm이 클로징을 다시 눌러 작아지는 현상을 막는다.
    """
    valid = [c for c in chunk_paths if c.exists() and c.stat().st_size > 0]
    if not valid:
        raise RuntimeError("유효한 TTS 청크 없음")
    concat_file = output_path.parent / "tts_concat.txt"
    concat_file.write_text("".join(f"file '{c.resolve()}'\n" for c in valid), encoding="utf-8")
    raw_merged = output_path.parent / f"{output_path.stem}_rawconcat{output_path.suffix}"
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0",
             "-i", str(concat_file), "-c", "copy", str(raw_merged)],
            capture_output=True, check=True, timeout=120,
        )
        # Global EBU R128 pass across the whole narration (per-chunk loudnorm alone
        # still leaves audible jumps between scenes).
        try:
            from config.settings import TTS_LOUDNORM_ENABLED, TTS_LOUDNORM_PARAMS
        except Exception:
            TTS_LOUDNORM_ENABLED, TTS_LOUDNORM_PARAMS = True, "I=-16:TP=-1.5:LRA=11"
        if TTS_LOUDNORM_ENABLED and not skip_global_loudnorm:
            try:
                subprocess.run(
                    [
                        "ffmpeg", "-y", "-i", str(raw_merged),
                        "-af", f"loudnorm={TTS_LOUDNORM_PARAMS}",
                        "-ar", "44100", "-ac", "1", "-c:a", "pcm_s16le",
                        str(output_path),
                    ],
                    capture_output=True, check=True, timeout=180,
                )
            except Exception:
                # Keep concat audio rather than failing the whole render.
                raw_merged.replace(output_path)
        else:
            raw_merged.replace(output_path)
    finally:
        concat_file.unlink(missing_ok=True)
        raw_merged.unlink(missing_ok=True)
