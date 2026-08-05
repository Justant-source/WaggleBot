"""TTS 발화 정렬과 텍스트 선행 화면 타임라인 단위 테스트."""

import wave
from pathlib import Path

import pytest

from ai_worker.renderer.layout import (
    _STATIC_CONCAT_CFR_ARGS,
    _STATIC_FINAL_FRAME_HOLD_FILTER,
    _append_text_only_line,
    _build_static_concat_manifest,
    _build_visual_timeline,
    _cap_output_to_audio,
)
from ai_worker.tts.alignment import TimedWord, align_words_to_lines


def test_alignment_returns_actual_line_starts() -> None:
    """원문 줄은 글자 수가 아니라 전사된 첫 단어 시각으로 정렬한다."""
    result = align_words_to_lines(
        ["첫 번째 문장", "두 번째 문장", "세 번째 문장"],
        [
            TimedWord("첫", 0.08, 0.24),
            TimedWord("번째", 0.24, 0.47),
            TimedWord("문장", 0.47, 0.76),
            TimedWord("두", 1.12, 1.25),
            TimedWord("번째", 1.25, 1.51),
            TimedWord("문장", 1.51, 1.83),
            TimedWord("세", 2.17, 2.30),
            TimedWord("번째", 2.30, 2.55),
            TimedWord("문장", 2.55, 2.88),
        ],
    )

    assert result is not None
    starts, confidence = result
    assert starts == [0.08, 1.12, 2.17]
    assert confidence == 1.0


def test_alignment_rejects_low_confidence_transcript() -> None:
    assert align_words_to_lines(
        ["정확한 원문", "두번째 원문"],
        [TimedWord("전혀다른말", 0.0, 0.4)],
        min_confidence=0.9,
    ) is None


def test_visual_timeline_leads_body_but_not_outro() -> None:
    """본문은 150ms 선행하지만 outro는 prior visual의 250ms hold 뒤에 시작한다."""
    frames = [Path("one.png"), Path("two.png"), Path("three.png")]
    plan = [{"sent_idx": 0}, {"sent_idx": 1}, {"sent_idx": 2, "type": "outro"}]
    # The second audio chunk already includes the 250ms closing pre-pause.
    timeline = _build_visual_timeline(frames, plan, [2.0, 1.25, 3.0])

    assert timeline == [
        (frames[0], 1.85), (frames[1], 0.15),
        (frames[1], 1.25),
        (frames[2], 3.0),
    ]
    assert sum(duration for _, duration in timeline) == 6.25


def test_visual_timeline_does_not_advance_to_silent_frame() -> None:
    frames = [Path("spoken.png"), Path("decorative.png")]
    timeline = _build_visual_timeline(
        frames,
        [{"sent_idx": 0}, {"sent_idx": None}],
        [1.0, 0.5],
    )

    assert timeline == [(frames[0], 1.0), (frames[1], 0.5)]


def test_text_only_lines_accumulate_three_then_reset() -> None:
    history: list[dict] = []
    for text in ("첫 줄", "둘째 줄", "셋째 줄"):
        history = _append_text_only_line(history, [text], "body", max_slots=3)

    assert [item["lines"] for item in history] == [["첫 줄"], ["둘째 줄"], ["셋째 줄"]]
    history = _append_text_only_line(history, ["새 묶음 첫 줄"], "body", max_slots=3)
    assert history == [{"lines": ["새 묶음 첫 줄"], "block_type": "body"}]


def test_pre_split_text_only_lines_become_sequential_plan_entries() -> None:
    from ai_worker.renderer.layout import _scenes_to_plan_and_sentences
    from ai_worker.scene.director import SceneDecision

    scene = SceneDecision(
        type="text_only",
        text_lines=["첫 줄 둘째 줄 셋째 줄"],
        image_url=None,
        pre_split_lines=["첫 줄", "둘째 줄", "셋째 줄"],
    )
    sentences, plan, _images = _scenes_to_plan_and_sentences([scene])

    assert [sentence["text"] for sentence in sentences] == ["첫 줄", "둘째 줄", "셋째 줄"]
    assert [entry["sent_idx"] for entry in plan] == [0, 1, 2]


def test_final_mux_is_capped_to_audio_timeline() -> None:
    capped = _cap_output_to_audio(["ffmpeg", "-i", "video.mp4", "out.mp4"], 52.626)

    assert capped == [
        "ffmpeg", "-i", "video.mp4", "-t", "52.626000", "-shortest", "out.mp4",
    ]


def test_static_concat_manifest_uses_filter_owned_final_frame_hold() -> None:
    """Tpad, not a terminal duplicate, owns the final still-image hold."""
    first = Path("first.png")
    closing = Path("closing.png")
    manifest = _build_static_concat_manifest([(first, 1.25), (closing, 3.438844)])
    lines = manifest.splitlines()

    assert lines[1] == "duration 1.250000"
    assert lines[3] == "duration 3.438844"
    assert lines[-1] == "duration 3.438844"
    assert lines.count(f"file '{closing.resolve()}'") == 1
    assert _STATIC_CONCAT_CFR_ARGS == ["-vsync", "cfr", "-r", "30"]
    assert _STATIC_FINAL_FRAME_HOLD_FILTER == "tpad=stop_mode=clone:stop=-1"


def test_outro_uses_existing_95ms_lead_plus_55ms_pad_and_500ms_tail(tmp_path: Path, monkeypatch) -> None:
    """The closing preserves 250ms hold and pads only missing lead silence."""
    from ai_worker.renderer import _tts

    (tmp_path / "chunk_000.wav").touch()
    (tmp_path / "chunk_001.wav").touch()
    calls: list[tuple[str, Path, float]] = []

    def append_silence(path: Path, seconds: float) -> float:
        calls.append(("append", path, seconds))
        return 1.25 if path.name == "chunk_000.wav" else 2.555

    def prepend_silence(path: Path, seconds: float) -> float:
        calls.append(("prepend", path, seconds))
        return 2.055

    monkeypatch.setattr(_tts, "_append_silence", append_silence)
    monkeypatch.setattr(_tts, "_prepend_silence", prepend_silence)
    monkeypatch.setattr(_tts, "_measure_leading_silence", lambda _: 0.095)
    durations = _tts._apply_outro_timing(
        [{"type": "comments"}, {"type": "outro"}], [1.0, 2.0], tmp_path,
    )

    assert [(kind, path.name) for kind, path, _seconds in calls] == [
        ("append", "chunk_000.wav"),
        ("prepend", "chunk_001.wav"),
        ("append", "chunk_001.wav"),
    ]
    assert abs(calls[0][2] - 0.25) < 1e-9
    assert abs(calls[1][2] - 0.055) < 1e-9
    assert abs(calls[2][2] - 0.50) < 1e-9
    assert durations == [1.25, 2.555]


def test_measure_leading_pcm_silence_without_trimming(tmp_path: Path) -> None:
    """-45 dBFS keeps low-level pre-speech noise inside the measured 95ms lead."""
    from ai_worker.renderer._tts import _measure_leading_silence

    sample_rate = 44_100
    silent_frames = round(sample_rate * 0.095)
    wav_path = tmp_path / "outro.wav"
    with wave.open(str(wav_path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        # 100/32768 ≈ -50 dBFS: measurable waveform noise, but quieter than
        # the -45 dBFS speech threshold used for lead timing.
        wav_file.writeframes((100).to_bytes(2, "little", signed=True) * silent_frames)
        wav_file.writeframes(b"\xff\x7f" * 100)

    measured = _measure_leading_silence(wav_path)
    assert abs(measured - (silent_frames / sample_rate)) < (1 / sample_rate)


def test_leading_silence_ignores_brief_loud_click_before_speech(tmp_path: Path) -> None:
    """Three-frame debounce prevents a transient click from shortening outro lead."""
    from ai_worker.renderer._tts import _measure_leading_silence

    sample_rate = 44_100
    quiet_before_click = 20
    click_frames = 2
    quiet_after_click = 30
    expected_start = quiet_before_click + click_frames + quiet_after_click
    wav_path = tmp_path / "outro_click.wav"
    with wave.open(str(wav_path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(b"\x00\x00" * quiet_before_click)
        wav_file.writeframes((500).to_bytes(2, "little", signed=True) * click_frames)
        wav_file.writeframes(b"\x00\x00" * quiet_after_click)
        wav_file.writeframes((1_000).to_bytes(2, "little", signed=True) * 10)

    measured = _measure_leading_silence(wav_path)
    assert abs(measured - (expected_start / sample_rate)) < (1 / sample_rate)


def test_initial_text_lead_pads_only_missing_native_pcm_silence(tmp_path: Path, monkeypatch) -> None:
    """A Fish WAV's 118ms native lead receives only the missing 32ms."""
    from ai_worker.renderer import _tts

    wav_path = tmp_path / "narration_first.wav"
    wav_path.touch()
    calls: list[float] = []
    monkeypatch.setattr(_tts, "_measure_leading_silence", lambda _: 0.118)
    monkeypatch.setattr(
        _tts,
        "_prepend_silence",
        lambda _path, seconds: calls.append(seconds) or 2.118,
    )

    duration = _tts._ensure_initial_text_lead(wav_path, 0.150)

    assert calls == [0.032]
    assert duration == 2.118


def test_initial_text_lead_does_not_stack_on_long_native_silence(tmp_path: Path, monkeypatch) -> None:
    """A 267.596ms native lead already satisfies the 150ms text contract."""
    from ai_worker.renderer import _tts

    wav_path = tmp_path / "narration_first.wav"
    wav_path.touch()
    monkeypatch.setattr(_tts, "_measure_leading_silence", lambda _: 0.267596)
    monkeypatch.setattr(_tts, "_prepend_silence", lambda *_: pytest.fail("must not pad"))
    monkeypatch.setattr(_tts, "_get_audio_duration", lambda _: 2.267596)

    assert _tts._ensure_initial_text_lead(wav_path, 0.150) == 2.267596


def test_tts_cache_key_invalidates_pre_1_1x_audio() -> None:
    """Speed/post-process changes must not reuse a pp_v3 (1.2x) narrator WAV."""
    from ai_worker.core.processor import _tts_cache_key
    from config.settings import TTS_SPEED

    key = _tts_cache_key("yohan", "캐시 검증 대사")

    assert key == f"yohan:캐시 검증 대사:{TTS_SPEED:.3f}:pp_v4"
    assert "pp_v3" not in key


def test_huggingface_cache_is_writable_before_whisper_import(monkeypatch) -> None:
    """HF/Xet must never fall back to the uid-1000 worker's `/.cache`."""
    import os
    from config.settings import (
        HF_HOME,
        HF_HUB_CACHE,
        HF_XET_CACHE,
        XDG_CACHE_HOME,
        WHISPER_DOWNLOAD_ROOT,
        configure_huggingface_cache,
    )

    for name in ("HF_HOME", "HF_HUB_CACHE", "HF_XET_CACHE", "XDG_CACHE_HOME", "HF_HUB_DISABLE_XET"):
        monkeypatch.delenv(name, raising=False)
    configure_huggingface_cache()

    assert os.environ["HF_HOME"] == str(HF_HOME)
    assert os.environ["HF_HUB_CACHE"] == str(HF_HUB_CACHE)
    assert os.environ["HF_XET_CACHE"] == str(HF_XET_CACHE)
    assert os.environ["XDG_CACHE_HOME"] == str(XDG_CACHE_HOME)
    assert os.environ["HF_HUB_DISABLE_XET"] == "1"
    assert all(path.is_relative_to(WHISPER_DOWNLOAD_ROOT) for path in (HF_HOME, HF_HUB_CACHE, HF_XET_CACHE, XDG_CACHE_HOME))
    assert all(path.is_dir() for path in (HF_HOME, HF_HUB_CACHE, HF_XET_CACHE, XDG_CACHE_HOME))
