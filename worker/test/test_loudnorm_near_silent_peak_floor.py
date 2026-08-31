"""Near-silent ASR mis-cuts must reach a usable speech peak after loudnorm."""
from __future__ import annotations

import subprocess
from pathlib import Path

from ai_worker.renderer._tts import _loudnorm_inplace


def _make_sine(path: Path, *, volume_db: float, seconds: float = 1.2) -> None:
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", f"sine=frequency=440:sample_rate=44100:duration={seconds}",
            "-af", f"volume={volume_db}dB",
            "-ac", "1", "-c:a", "pcm_s16le",
            str(path),
        ],
        check=True, capture_output=True, timeout=30,
    )


def _measure_peak(path: Path) -> float:
    vd = subprocess.run(
        ["ffmpeg", "-y", "-i", str(path), "-af", "volumedetect", "-f", "null", "-"],
        capture_output=True, text=True, timeout=30,
    )
    for line in (vd.stderr or "").splitlines():
        if "max_volume:" in line:
            return float(line.split("max_volume:")[1].strip().split()[0])
    raise AssertionError("max_volume not found")


def test_near_silent_clip_reaches_speech_peak(tmp_path: Path):
    # Matches mis-aligned narration splits around -45 dBFS peak (job 10026251).
    wav = tmp_path / "near_silent.wav"
    _make_sine(wav, volume_db=-45.0)
    before = _measure_peak(wav)
    assert before < -40.0

    _loudnorm_inplace(wav)

    after = _measure_peak(wav)
    # Peak floor / raised gain ceiling should lift into a usable speech range.
    assert after >= -8.0, f"peak still too quiet: before={before} after={after}"
    assert after <= -0.3, f"peak too hot after floor: {after}"
