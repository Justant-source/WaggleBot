"""Body/fallback speech chunks must be loudnormed; merge skips unsafe global pass."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TTS = (ROOT / "ai_worker/renderer/_tts.py").read_text(encoding="utf-8")
LAYOUT = (ROOT / "ai_worker/renderer/layout.py").read_text(encoding="utf-8")


def test_body_tts_path_loudnorms_unconditionally():
    gated = (
        'if scene_type in ("comments", "chat"):\n'
        "                    _loudnorm_inplace(chunk_path)"
    )
    assert gated not in TTS
    assert "Fish 저음량 클립이 그대로 실려" in TTS


def test_narration_split_chunks_are_loudnormed():
    assert "Narration splits can include near-silent" in TTS


def test_merge_skips_global_after_per_chunk_loudnorm():
    assert "skip_global_loudnorm=True" in LAYOUT
    assert "skip_global_loudnorm=(narration_audio is not None)" not in LAYOUT
