"""TTS quality gate: reject script-absent Hangul inserts (language bleed)."""

from ai_worker.tts.quality import (
    assess_transcript,
    unexpected_hangul_inserts,
)


def test_unexpected_insert_detects_foreign_bleed_hangul():
    expected = (
        "직접 말할 거리도 없어서 그냥 무시해봤거든요 "
        "근데 무시했을 때 그 친구 반응이 가관이에요"
    )
    transcript = (
        "직접 말할 거리도 없어서 그냥 무시해봤거든요 "
        "아침에 탈 때 "
        "근데 무시했을 때 그 친구 반응이 가관이에요"
    )
    inserts = unexpected_hangul_inserts(expected, transcript)
    assert any("아침" in frag for frag in inserts), inserts
    quality = assess_transcript(expected, transcript, asr_confidence=0.9)
    assert quality.requires_retry
    assert quality.reason == "unexpected_speech_insert"


def test_latin_asr_junk_does_not_count_as_insert():
    expected = "전혀 안 먹히더라고요"
    transcript = "ngulo 전혀 안 먹히더라고요 analyt"
    assert unexpected_hangul_inserts(expected, transcript) == ()
    quality = assess_transcript(expected, transcript, asr_confidence=0.9)
    assert quality.status == "passed"


def test_unexpected_insert_ignores_duplication_of_expected():
    expected = "그냥 무시해봤거든요 근데 무시했을 때"
    transcript = "그냥 무시해봤거든요 무시해봤거든요 근데 무시했을 때"
    assert unexpected_hangul_inserts(expected, transcript) == ()
    quality = assess_transcript(expected, transcript, asr_confidence=0.9)
    assert quality.status == "passed"


def test_clean_korean_transcript_passes():
    expected = "전혀 안 먹히더라고요"
    transcript = "전혀 안 먹히더라고요"
    assert unexpected_hangul_inserts(expected, transcript) == ()
    quality = assess_transcript(expected, transcript, asr_confidence=0.9)
    assert quality.status == "passed"
    assert quality.reason == "matched"
