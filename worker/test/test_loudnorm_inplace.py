"""댓글/outro 짧은 클립 양방향 loudnorm 검증."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from ai_worker.renderer._tts import _loudnorm_inplace


def _make_sine(path: Path, *, volume_db: float, seconds: float = 1.2) -> None:
    """Generate a mono 440Hz sine at approximate amplitude volume_db."""
    # volume filter: 0dB ≈ full scale; negative = quieter
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


def _measure_i(path: Path) -> float:
    check = subprocess.run(
        [
            "ffmpeg", "-y", "-i", str(path),
            "-af", "loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json",
            "-f", "null", "-",
        ],
        capture_output=True, text=True, timeout=60,
    )
    stderr = check.stderr or ""
    j0, j1 = stderr.rfind("{"), stderr.rfind("}")
    import json
    data = json.loads(stderr[j0:j1 + 1])
    return float(data["input_i"])


@pytest.mark.parametrize("volume_db", [-1.0, -28.0])
def test_loudnorm_brings_loud_and_quiet_into_band(tmp_path: Path, volume_db: float):
    wav = tmp_path / f"clip_{volume_db}.wav"
    _make_sine(wav, volume_db=volume_db)
    before_peak = _measure_peak(wav)

    _loudnorm_inplace(wav)

    after_i = _measure_i(wav)
    after_peak = _measure_peak(wav)
    # Target I=-16 with ±3 / +2 band used by implementation
    assert -20.0 <= after_i <= -13.0, f"I={after_i} still off-target (in peak={before_peak})"
    assert after_peak <= -0.5, f"peak={after_peak} still hot"
