"""ai_worker/renderer/_tts.py — TTS 청크 생성·병합 로직 (internal)"""

import logging
import re
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

_INTRO_PAUSE_SEC: float = 0.5  # 제목 읽기 후 본문 시작 전 숨고르기 (초)


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


def _split_wav_by_char_weights(
    src: Path,
    texts: list[str],
    out_paths: list[Path],
) -> list[float]:
    """하나의 낭독 wav를 글자 수 비율로 분할한다. 반환: 각 조각 duration(초)."""
    if len(texts) != len(out_paths):
        raise ValueError("texts/out_paths length mismatch")
    if not texts:
        return []
    total_dur = _get_audio_duration(src)
    weights = [max(len((t or "").strip()), 1) for t in texts]
    wsum = float(sum(weights))
    durations: list[float] = []
    cursor = 0.0
    for i, (w, out_p) in enumerate(zip(weights, out_paths)):
        if i == len(weights) - 1:
            seg = max(total_dur - cursor, 0.05)
        else:
            seg = max(total_dur * (w / wsum), 0.05)
        # slight overlap avoidance: clamp
        if cursor + seg > total_dur + 0.01:
            seg = max(total_dur - cursor, 0.05)
        # atrim in filter graph (NOT -ss after -i + afade — that combo zeros audio).
        # tiny afade hides hard-cut clicks at scene joins.
        fade = min(0.012, max(seg * 0.08, 0.004))
        fade_out_st = max(seg - fade, 0.0)
        af = (
            f"atrim=start={cursor:.4f}:duration={seg:.4f},asetpts=PTS-STARTPTS,"
            f"afade=t=in:st=0:d={fade:.4f},afade=t=out:st={fade_out_st:.4f}:d={fade:.4f}"
        )
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
                "[tts] narration split failed i=%d — silence fallback (%s)",
                i, (result.stderr[-200:] if result.stderr else b"").decode(errors="replace"),
            )
            subprocess.run(
                [
                    "ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
                    "-t", f"{seg:.4f}", "-c:a", "pcm_s16le", str(out_p),
                ],
                capture_output=True, check=True, timeout=10,
            )
        actual = _get_audio_duration(out_p) if out_p.exists() else seg
        durations.append(actual)
        cursor += seg
    logger.info(
        "[tts] narration split: src=%.1fs → %d parts (weights=%s)",
        total_dur, len(durations), weights,
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
    """짧은 클립(댓글/outro)도 본문과 같은 음량으로 맞춘다.

    단일 패스 loudnorm은 1~2초 클립에서 I=-34처럼 측정이 붕괴되어
    오히려 더 작아지거나 펌핑 노이즈가 난다 → 2-pass + 실패 시 peak gain.
    """
    import json as _json
    try:
        from config.settings import TTS_LOUDNORM_ENABLED, TTS_LOUDNORM_PARAMS
    except Exception:
        TTS_LOUDNORM_ENABLED, TTS_LOUDNORM_PARAMS = True, "I=-16:TP=-1.5:LRA=11"
    if not TTS_LOUDNORM_ENABLED or not wav_path.exists():
        return

    # parse I=/TP=/LRA= from params string
    target_i, target_tp, target_lra = -16.0, -1.5, 11.0
    for part in (TTS_LOUDNORM_PARAMS or "").split(":"):
        if part.startswith("I="):
            try: target_i = float(part[2:])
            except ValueError: pass
        elif part.startswith("TP="):
            try: target_tp = float(part[3:])
            except ValueError: pass
        elif part.startswith("LRA="):
            try: target_lra = float(part[4:])
            except ValueError: pass

    tmp = wav_path.with_suffix(".ln.wav")
    try:
        # Pass 1 — measure
        measure = subprocess.run(
            [
                "ffmpeg", "-y", "-i", str(wav_path),
                "-af", f"loudnorm=I={target_i}:TP={target_tp}:LRA={target_lra}:print_format=json",
                "-f", "null", "-",
            ],
            capture_output=True, text=True, timeout=60,
        )
        stderr = measure.stderr or ""
        # JSON is at the end of stderr
        jstart = stderr.rfind("{")
        jend = stderr.rfind("}")
        measured = {}
        if jstart >= 0 and jend > jstart:
            try:
                measured = _json.loads(stderr[jstart:jend + 1])
            except Exception:
                measured = {}

        mi = measured.get("input_i")
        mtp = measured.get("input_tp")
        mlra = measured.get("input_lra")
        mth = measured.get("input_thresh")
        # Pass 2 — apply with measured values (linear)
        if mi is not None and mtp is not None and mth is not None:
            af = (
                f"loudnorm=I={target_i}:TP={target_tp}:LRA={target_lra}"
                f":measured_I={mi}:measured_TP={mtp}"
                f":measured_LRA={mlra if mlra is not None else 0}"
                f":measured_thresh={mth}:linear=true:print_format=summary"
            )
            result = subprocess.run(
                [
                    "ffmpeg", "-y", "-i", str(wav_path),
                    "-af", af,
                    "-ar", "44100", "-ac", "1", "-c:a", "pcm_s16le", str(tmp),
                ],
                capture_output=True, text=True, timeout=60,
            )
            if result.returncode == 0 and tmp.exists() and tmp.stat().st_size > 64:
                # Verify we actually got near target; short clips can still fail
                check = subprocess.run(
                    [
                        "ffmpeg", "-y", "-i", str(tmp),
                        "-af", f"loudnorm=I={target_i}:TP={target_tp}:LRA={target_lra}:print_format=json",
                        "-f", "null", "-",
                    ],
                    capture_output=True, text=True, timeout=60,
                )
                cs = check.stderr or ""
                c0, c1 = cs.rfind("{"), cs.rfind("}")
                out_i = None
                if c0 >= 0 and c1 > c0:
                    try:
                        out_i = float(_json.loads(cs[c0:c1 + 1]).get("input_i", "nan"))
                    except Exception:
                        out_i = None
                if out_i is not None and out_i > target_i - 6:  # e.g. >= -22
                    tmp.replace(wav_path)
                    logger.info("[tts] 2-pass loudnorm ok %s → I≈%.1f", wav_path.name, out_i)
                    return
                logger.warning(
                    "[tts] 2-pass loudnorm still quiet (I≈%s) — peak gain fallback %s",
                    out_i, wav_path.name,
                )
                tmp.unlink(missing_ok=True)

        # Fallback: raise true peak toward target_tp (≈ -1.5 dBTP)
        # Measure peak with volumedetect
        vd = subprocess.run(
            ["ffmpeg", "-y", "-i", str(wav_path), "-af", "volumedetect", "-f", "null", "-"],
            capture_output=True, text=True, timeout=30,
        )
        max_vol = None
        for line in (vd.stderr or "").splitlines():
            if "max_volume:" in line:
                try:
                    max_vol = float(line.split("max_volume:")[1].strip().split()[0])
                except Exception:
                    pass
        if max_vol is None:
            return
        # Aim peak at about -1.5 dBTP
        gain = (target_tp - 0.5) - max_vol  # e.g. -2 - (-19) = +17 dB
        gain = max(0.0, min(gain, 24.0))
        if gain < 0.5:
            return
        result = subprocess.run(
            [
                "ffmpeg", "-y", "-i", str(wav_path),
                "-af", f"volume={gain:.2f}dB",
                "-ar", "44100", "-ac", "1", "-c:a", "pcm_s16le", str(tmp),
            ],
            capture_output=True, check=True, timeout=30,
        )
        if tmp.exists() and tmp.stat().st_size > 64:
            tmp.replace(wav_path)
            logger.info("[tts] peak gain +%.1fdB applied to %s", gain, wav_path.name)
    except Exception:
        logger.warning("[tts] loudnorm failed for %s", wav_path.name, exc_info=True)
        tmp.unlink(missing_ok=True)



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

    narration_audio가 있으면 hook/body 구간은 통합 낭독 wav를 글자 수 비율로
    분할해 쓰고(장면별 Fish Speech 재호출 없음), closer·댓글·채팅만 개별 합성한다.
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
                part_durs = _split_wav_by_char_weights(
                    Path(narration_audio), narrator_texts, out_paths,
                )
                for fi, dur in zip(narrator_frames, part_durs):
                    durations[fi] = dur
                logger.info(
                    "[layout] narration wav 재사용: %d frames from %s",
                    len(narrator_frames), Path(narration_audio).name,
                )
            except Exception:
                logger.warning(
                    "[layout] narration split 실패 — 장면별 TTS 폴백",
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
            if scene_type == "intro" and dur > 0:
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
                # 댓글 등은 본문 통합 wav와 음량 맞춤 (outro는 캐시 단계에서 이미 loudnorm)
                if scene_type in ("comments", "chat") and not pre_audio:
                    _loudnorm_inplace(chunk_path)
                dur = _get_audio_duration(chunk_path)

            if scene_type == "intro" and dur > 0:
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
    return durations



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

