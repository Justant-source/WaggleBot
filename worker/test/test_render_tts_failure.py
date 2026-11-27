"""렌더 단계 청크 TTS 실패가 무음 클립으로 삼켜지지 않고 렌더 실패로 전파되는지 검증한다.

배경: 예전에는 재시도 후에도 실패하면 길이 0 청크로 반환해 대사가 빠진 영상이 정상 산출물처럼
남았다. 이제 TTSUnavailable은 그대로(재큐), 그 외 합성 실패는 TTSError로 올려 렌더를 실패시킨다.
빈 텍스트(공백·정규화 후 빈 문장)만 건너뛴다. Local-TTS 서버는 호출하지 않는다.
"""
import asyncio
from pathlib import Path

import pytest

from ai_worker.renderer import _tts
from ai_worker.tts import synth

pytestmark = pytest.mark.unit


@pytest.fixture()
def fake(monkeypatch):
    state = {"calls": 0, "exc": None}

    async def fake_synthesize(text, scene_type="image_text", voice_key=None, output_path=None,
                              emotion="", post_id=None):
        state["calls"] += 1
        if state["exc"] is not None:
            raise state["exc"]
        Path(output_path).write_bytes(b"x" * 2048)
        return Path(output_path)

    async def no_sleep(_):
        return None

    monkeypatch.setattr(synth, "synthesize", fake_synthesize)
    monkeypatch.setattr(asyncio, "sleep", no_sleep)
    monkeypatch.setattr(_tts, "_get_audio_duration", lambda p: 1.0)
    monkeypatch.setattr(_tts, "_loudnorm_inplace", lambda p: None)
    return state


def _run(text, tmp_path, scene="image_text"):
    return asyncio.run(_tts._tts_chunk_async(text, 3, tmp_path, scene, None, "F1", post_id=7))


def test_tts_error_after_retry_raises_instead_of_silent_chunk(fake, tmp_path):
    fake["exc"] = synth.TTSError("job 영구 실패")
    with pytest.raises(synth.TTSError) as ei:
        _run("본문 문장", tmp_path)
    assert fake["calls"] == 2                      # 1회 재시도 후 포기
    assert not isinstance(ei.value, synth.TTSUnavailable)
    assert "청크 3" in str(ei.value) and "job 영구 실패" in str(ei.value)


def test_unexpected_exception_also_fails_render(fake, tmp_path):
    fake["exc"] = OSError("disk full")
    with pytest.raises(synth.TTSError):
        _run("본문 문장", tmp_path, scene="outro")
    assert fake["calls"] == 2


def test_tts_unavailable_propagates_without_retry(fake, tmp_path):
    fake["exc"] = synth.TTSUnavailable("서버 불가")
    with pytest.raises(synth.TTSUnavailable):
        _run("본문 문장", tmp_path)
    assert fake["calls"] == 1


def test_first_failure_then_success_recovers(monkeypatch, fake, tmp_path):
    seq = [synth.TTSError("일시"), None]

    async def flaky(text, scene_type="image_text", voice_key=None, output_path=None,
                    emotion="", post_id=None):
        e = seq.pop(0)
        if e:
            raise e
        Path(output_path).write_bytes(b"x" * 2048)

    monkeypatch.setattr(synth, "synthesize", flaky)
    assert _run("본문 문장", tmp_path) == 1.0


@pytest.mark.parametrize("text", ["", "   ", "\n"])
def test_blank_text_skipped_without_synthesis(fake, tmp_path, text):
    assert _run(text, tmp_path) == 0.0
    assert fake["calls"] == 0


def test_text_empty_after_normalization_is_skipped(fake, tmp_path):
    fake["exc"] = ValueError("TTS 입력 텍스트가 정규화 후 비어있음")
    assert _run("...", tmp_path) == 0.0
    assert fake["calls"] == 1                       # 재시도하지 않음


def test_generate_chunks_propagates_failure(fake, tmp_path):
    fake["exc"] = synth.TTSError("boom")
    plan = [{"type": "image_text", "sent_idx": 0}]
    with pytest.raises(synth.TTSError):
        asyncio.run(_tts._generate_tts_chunks(plan, [{"text": "본문 문장"}], tmp_path, "F1", "+0%",
                                              post_id=7))
