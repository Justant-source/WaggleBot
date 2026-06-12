"""음성 자산 등록 CLI — 녹음 → 정제·세그먼트 → faster-whisper 전사 → 참조 음성 등록.

ai_worker 컨테이너 안에서 실행한다 (faster-whisper·ffmpeg 의존):

    docker compose -f env/docker-compose.yml exec ai_worker \\
        python -m tools.prepare_voice --input assets/voices_raw/myvoice.wav --key myvoice --label "내 목소리"

동작:
  1. 입력 오디오를 mono/44.1kHz/16bit + loudnorm + 가장자리 무음 트림으로 정제
  2. 무음 경계 기준 8~15초 세그먼트로 분할, 최장 N개(합계 ≤30초) 선별
  3. faster-whisper(ko)로 각 세그먼트 전사 → .lab (또는 --transcript 단일 클립)
  4. assets/voices/<key>/NN.wav + NN.lab 기록 (폴더엔 참조쌍만)
  5. config/voices.json 갱신 (ref_dir=<key>, file=<key>/01.wav)

주의: 동일 key 재등록 시 fish-speech 메모리 캐시(reference_id 기준)가 스테일해지므로
      fish-speech 컨테이너를 재시작해야 새 음성이 반영된다.
"""
import argparse
import json
import logging
import re
import subprocess
import sys
import tempfile
from pathlib import Path

# config 패키지를 sys.path에서 찾을 수 있게 보장 (python -m tools.prepare_voice를
# /app(컨테이너) 또는 repo 루트(호스트)에서 실행하는 두 경우 모두 지원).
_THIS = Path(__file__).resolve()
for _cand in (_THIS.parent.parent, _THIS.parent.parent.parent):
    if (_cand / "config" / "settings.py").exists():
        if str(_cand) not in sys.path:
            sys.path.insert(0, str(_cand))
        break

from config import settings as _cfg  # noqa: E402
from config.settings import (  # noqa: E402
    ASSETS_DIR,
    VOICE_REFERENCE_TEXTS,
    WHISPER_COMPUTE_TYPE,
    WHISPER_DEVICE,
    WHISPER_DOWNLOAD_ROOT,
    WHISPER_MODEL,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)-5s %(message)s")
logger = logging.getLogger("prepare_voice")

# settings 모듈 위치 기준 경로 (컨테이너 /app/config, 호스트 repo/config 모두 정확)
_CONFIG_DIR = Path(_cfg.__file__).resolve().parent
APP_ROOT = _CONFIG_DIR.parent                 # config/의 상위 = /app(컨테이너) | repo(호스트)
VOICES_DIR = ASSETS_DIR / "voices"
VOICES_JSON = _CONFIG_DIR / "voices.json"
_AUDIO_EXTS = (".wav", ".mp3", ".flac", ".m4a", ".ogg", ".aac", ".opus")

# 세그먼트 길이 정책 (초)
_MIN_CLIP_S = 8.0
_MAX_CLIP_S = 15.0
_TARGET_CLIP_S = 11.0


def _run(cmd: list[str], timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def _ffprobe_duration(path: Path) -> float:
    r = _run([
        "ffprobe", "-v", "quiet", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(path),
    ])
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def _convert_clean(src: Path, dst: Path) -> None:
    """mono/44.1kHz/16bit + loudnorm + 가장자리 무음 트림으로 정제."""
    r = _run([
        "ffmpeg", "-y", "-i", str(src),
        "-af", (
            "loudnorm=I=-16:TP=-1.5:LRA=11,"
            "silenceremove=start_periods=1:start_silence=0.1:start_threshold=-45dB,"
            "areverse,"
            "silenceremove=start_periods=1:start_silence=0.1:start_threshold=-45dB,"
            "areverse"
        ),
        "-ar", "44100", "-ac", "1", "-c:a", "pcm_s16le", str(dst),
    ], timeout=180)
    if r.returncode != 0 or not dst.exists():
        raise RuntimeError(f"ffmpeg 정제 실패: {r.stderr[-300:]}")


def _detect_silences(path: Path, noise_db: int = -30, min_dur: float = 0.3) -> list[tuple[float, float]]:
    """ffmpeg silencedetect → (silence_start, silence_end) 목록."""
    r = _run([
        "ffmpeg", "-i", str(path),
        "-af", f"silencedetect=noise={noise_db}dB:d={min_dur}",
        "-f", "null", "-",
    ])
    starts = [float(m) for m in re.findall(r"silence_start:\s*([0-9.]+)", r.stderr)]
    ends = [float(m) for m in re.findall(r"silence_end:\s*([0-9.]+)", r.stderr)]
    return list(zip(starts, ends))


def _plan_segments(duration: float, silences: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """무음 중점을 경계 후보로 8~15초 클립을 계획. 무음 정보 없으면 균등 분할."""
    if duration <= _MAX_CLIP_S:
        return [(0.0, duration)]

    # 경계 후보 = 0, 각 무음 중점, duration
    boundaries = [0.0]
    for s_start, s_end in silences:
        mid = (s_start + s_end) / 2.0
        if mid - boundaries[-1] >= 1.0:
            boundaries.append(mid)
    if duration - boundaries[-1] >= 1.0:
        boundaries.append(duration)
    else:
        boundaries[-1] = duration

    clips: list[tuple[float, float]] = []
    seg_start = boundaries[0]
    for b in boundaries[1:]:
        length = b - seg_start
        if length >= _TARGET_CLIP_S:
            end = seg_start + min(length, _MAX_CLIP_S)
            clips.append((seg_start, end))
            seg_start = end
    # 잔여 구간
    if duration - seg_start >= _MIN_CLIP_S:
        clips.append((seg_start, min(seg_start + _MAX_CLIP_S, duration)))

    # 무음 경계로 한 클립도 못 만들면 균등 분할 폴백
    if not clips:
        n = max(1, int(duration // _TARGET_CLIP_S))
        step = duration / n
        clips = [(i * step, min((i + 1) * step, duration)) for i in range(n)]
    return clips


def _select_clips(
    clips: list[tuple[float, float]], max_refs: int, max_total_s: float,
) -> list[tuple[float, float]]:
    """긴 클립 우선으로 max_refs개·합계 ≤ max_total_s 선별 (원래 시간순 유지)."""
    ordered = sorted(clips, key=lambda c: -(c[1] - c[0]))
    picked: list[tuple[float, float]] = []
    total = 0.0
    for c in ordered:
        if len(picked) >= max_refs:
            break
        length = c[1] - c[0]
        if total + length > max_total_s and picked:
            continue
        picked.append(c)
        total += length
    return sorted(picked, key=lambda c: c[0])


def _extract_clip(src: Path, start: float, end: float, dst: Path) -> None:
    r = _run([
        "ffmpeg", "-y", "-i", str(src), "-ss", f"{start:.3f}", "-to", f"{end:.3f}",
        "-ar", "44100", "-ac", "1", "-c:a", "pcm_s16le", str(dst),
    ])
    if r.returncode != 0 or not dst.exists():
        raise RuntimeError(f"클립 추출 실패: {r.stderr[-200:]}")


def _load_whisper(model: str, device: str, compute_type: str):
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise SystemExit(
            "faster-whisper 미설치. ai_worker 이미지를 리빌드하세요:\n"
            "  docker compose -f env/docker-compose.yml build ai_worker\n"
            f"(원인: {exc})"
        )
    WHISPER_DOWNLOAD_ROOT.mkdir(parents=True, exist_ok=True)
    logger.info("faster-whisper 로드: model=%s device=%s compute=%s", model, device, compute_type)
    return WhisperModel(
        model, device=device, compute_type=compute_type,
        download_root=str(WHISPER_DOWNLOAD_ROOT),
    )


def _transcribe(whisper, path: Path) -> str:
    segments, _info = whisper.transcribe(str(path), language="ko", beam_size=5, vad_filter=True)
    text = " ".join(seg.text.strip() for seg in segments).strip()
    return re.sub(r"\s+", " ", text)


def _update_voices_json(key: str, label: str) -> None:
    """config/voices.json에 항목 추가/갱신 (타 항목·순서 보존)."""
    data: dict = {"version": 2, "voices": []}
    if VOICES_JSON.exists():
        try:
            data = json.loads(VOICES_JSON.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            logger.warning("voices.json 파싱 실패 — 새로 작성")
    data.setdefault("version", 2)
    voices = data.setdefault("voices", [])
    entry = {
        "key": key, "label": label, "ref_dir": key,
        "file": f"{key}/01.wav", "params": {},
    }
    for i, v in enumerate(voices):
        if v.get("key") == key:
            entry["params"] = v.get("params", {})  # 기존 파라미터 보존
            voices[i] = entry
            break
    else:
        voices.append(entry)
    VOICES_JSON.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    logger.info("voices.json 갱신: key=%s", key)


def prepare_voice(args: argparse.Namespace) -> int:
    src = Path(args.input)
    if not src.is_absolute():
        cand = (Path.cwd() / src)
        src = cand if cand.exists() else (APP_ROOT / src)
    src = src.resolve()
    if not src.exists():
        logger.error("입력 경로 없음: %s", src)
        return 1

    # 입력 오디오 수집
    if src.is_dir():
        inputs = sorted(p for p in src.iterdir() if p.suffix.lower() in _AUDIO_EXTS)
    else:
        inputs = [src]
    if not inputs:
        logger.error("오디오 파일 없음: %s", src)
        return 1

    out_dir = VOICES_DIR / args.key
    if out_dir.exists() and any(out_dir.iterdir()) and not args.force:
        logger.error("이미 존재: %s (덮어쓰려면 --force)", out_dir)
        return 1

    whisper = None
    if not args.transcript:
        whisper = _load_whisper(args.model, args.device, args.compute_type)

    with tempfile.TemporaryDirectory() as tmpd:
        tmp = Path(tmpd)
        # 1) 정제 + 세그먼트 계획 (여러 입력은 각각 처리 후 누적)
        planned: list[tuple[Path, float, float]] = []  # (cleaned_src, start, end)
        for idx, inp in enumerate(inputs):
            cleaned = tmp / f"clean_{idx}.wav"
            logger.info("정제 중: %s", inp.name)
            _convert_clean(inp, cleaned)
            dur = _ffprobe_duration(cleaned)
            if dur <= 0:
                logger.warning("길이 0 — 건너뜀: %s", inp.name)
                continue
            silences = _detect_silences(cleaned)
            for (s, e) in _plan_segments(dur, silences):
                planned.append((cleaned, s, e))

        if not planned:
            logger.error("유효한 세그먼트 없음")
            return 1

        # 2) 선별 (max_refs / max_total_secs)
        # planned을 (길이 기준) 선별하되 원본 순서 유지
        with_len = [(c, s, e, e - s) for (c, s, e) in planned]
        with_len.sort(key=lambda x: -x[3])
        picked: list[tuple[Path, float, float]] = []
        total = 0.0
        for (c, s, e, length) in with_len:
            if len(picked) >= args.max_refs:
                break
            if total + length > args.max_total_secs and picked:
                continue
            picked.append((c, s, e))
            total += length
        if not picked:
            picked = [(planned[0][0], planned[0][1], planned[0][2])]

        # 3) 클립 추출 + 전사 → 임시 기록
        results: list[tuple[Path, str]] = []
        for n, (c, s, e) in enumerate(picked, start=1):
            clip = tmp / f"{n:02d}.wav"
            _extract_clip(c, s, e, clip)
            if args.transcript:
                lab = args.transcript.strip()
            else:
                lab = _transcribe(whisper, clip)
            if not lab:
                logger.warning("전사 결과 비어 있음 — 클립 %d 건너뜀", n)
                continue
            results.append((clip, lab))
            logger.info("클립 %d (%.1f초): %s", n, e - s, lab[:60])

        if not results:
            logger.error("전사 가능한 클립 없음")
            return 1

        # 4) 출력 폴더에 기록 (참조쌍만)
        if out_dir.exists():
            for old in out_dir.iterdir():
                old.unlink()
        out_dir.mkdir(parents=True, exist_ok=True)
        for n, (clip, lab) in enumerate(results, start=1):
            (out_dir / f"{n:02d}.wav").write_bytes(clip.read_bytes())
            (out_dir / f"{n:02d}.lab").write_text(lab, encoding="utf-8")

    # 5) voices.json 갱신
    _update_voices_json(args.key, args.label or args.key)

    logger.info("=" * 56)
    logger.info("등록 완료: voice=%s, 참조 클립 %d개 → %s", args.key, len(results), out_dir)
    for n, (_clip, lab) in enumerate(results, start=1):
        logger.info("  %02d.lab: %s", n, lab)
    logger.info("=" * 56)
    logger.info("⚠ 적용하려면 fish-speech 재시작 (reference_id 메모리 캐시 갱신):")
    logger.info("  docker compose -f env/docker-compose.yml restart fish-speech")

    # 6) 미리듣기 (선택)
    if args.preview:
        _preview(args.key)
    return 0


def _preview(key: str) -> None:
    import asyncio
    from config.settings import MEDIA_DIR
    from ai_worker.tts.fish_client import synthesize

    out = Path(MEDIA_DIR) / "tmp" / f"voice_preview_{key}.wav"
    out.parent.mkdir(parents=True, exist_ok=True)
    text = VOICE_REFERENCE_TEXTS.get(key, "안녕하세요. 이 음성으로 합성한 미리듣기입니다.")
    logger.info("미리듣기 합성 중 (fish-speech 재시작 후 권장)...")
    try:
        asyncio.run(synthesize(text, voice_key=key, output_path=out))
        logger.info("미리듣기 저장: %s", out)
    except Exception as exc:
        logger.warning("미리듣기 실패 (fish-speech 미재시작?): %s", exc)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="음성 자산 등록 (faster-whisper 자동 전사)")
    p.add_argument("--input", required=True, help="녹음 파일 또는 디렉토리 (assets/voices_raw/ 권장)")
    p.add_argument("--key", required=True, help="음성 키 (assets/voices/<key>/, reference_id)")
    p.add_argument("--label", default="", help="대시보드 표시 라벨 (기본: key)")
    p.add_argument("--transcript", default="", help="수동 전사 (단일 클립 모드, whisper 미사용)")
    p.add_argument("--model", default=WHISPER_MODEL, help=f"whisper 모델 (기본: {WHISPER_MODEL})")
    p.add_argument("--device", default=WHISPER_DEVICE, help=f"cpu|cuda (기본: {WHISPER_DEVICE})")
    p.add_argument("--compute-type", default=WHISPER_COMPUTE_TYPE, dest="compute_type")
    p.add_argument("--max-refs", type=int, default=3, dest="max_refs", help="최대 참조 클립 수")
    p.add_argument("--max-total-secs", type=float, default=30.0, dest="max_total_secs")
    p.add_argument("--preview", action="store_true", help="등록 후 미리듣기 합성")
    p.add_argument("--force", action="store_true", help="기존 <key> 폴더 덮어쓰기")
    return p


def main() -> None:
    args = build_parser().parse_args()
    raise SystemExit(prepare_voice(args))


if __name__ == "__main__":
    main()
