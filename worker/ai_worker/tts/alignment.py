"""합성 음성과 대본 줄을 정렬해 실제 발화 시작 시각을 구한다."""

from __future__ import annotations

import difflib
import logging
import re
import threading
from dataclasses import dataclass
from pathlib import Path

from config.settings import (
    TTS_ALIGNMENT_COMPUTE_TYPE,
    TTS_ALIGNMENT_DEVICE,
    TTS_ALIGNMENT_MIN_CONFIDENCE,
    TTS_ALIGNMENT_MODEL,
    WHISPER_DOWNLOAD_ROOT,
    configure_huggingface_cache,
)

logger = logging.getLogger(__name__)

_MODEL = None
_MODEL_LOCK = threading.Lock()
_INFERENCE_LOCK = threading.Lock()
_KEEP_CHARS_RE = re.compile(r"[^0-9A-Za-z가-힣]+")


@dataclass(frozen=True)
class TimedWord:
    text: str
    start: float
    end: float
    probability: float = 1.0


def _compact(text: str) -> str:
    return _KEEP_CHARS_RE.sub("", (text or "").lower())


def align_words_to_lines(
    lines: list[str],
    words: list[TimedWord],
    *,
    min_confidence: float = TTS_ALIGNMENT_MIN_CONFIDENCE,
) -> tuple[list[float], float] | None:
    """ASR 단어열을 원문 줄에 문자 단위로 대응시켜 줄별 발화 시작을 반환한다."""
    expected_parts = [_compact(line) for line in lines]
    recognized_parts = [_compact(word.text) for word in words]
    if not expected_parts or any(not part for part in expected_parts):
        return None
    if not recognized_parts or any(not part for part in recognized_parts):
        return None

    expected = "".join(expected_parts)
    recognized = "".join(recognized_parts)
    matcher = difflib.SequenceMatcher(None, expected, recognized, autojunk=False)
    matching_chars = sum(block.size for block in matcher.get_matching_blocks())
    confidence = matching_chars / max(len(expected), 1)
    if confidence < min_confidence:
        logger.warning(
            "[tts-align] 정렬 신뢰도 부족: %.3f < %.3f",
            confidence,
            min_confidence,
        )
        return None

    anchors: dict[int, int] = {}
    for block in matcher.get_matching_blocks():
        for offset in range(block.size):
            anchors[block.a + offset] = block.b + offset
    anchor_keys = sorted(anchors)
    if not anchor_keys:
        return None

    word_ranges: list[tuple[int, int, TimedWord]] = []
    cursor = 0
    for part, word in zip(recognized_parts, words):
        word_ranges.append((cursor, cursor + len(part), word))
        cursor += len(part)

    def map_expected_pos(pos: int) -> int:
        if pos in anchors:
            return anchors[pos]
        left = max((key for key in anchor_keys if key < pos), default=None)
        right = min((key for key in anchor_keys if key > pos), default=None)
        if left is None:
            return max(0, anchors[right] - (right - pos))
        if right is None:
            return min(len(recognized) - 1, anchors[left] + (pos - left))
        ratio = (pos - left) / max(right - left, 1)
        return round(anchors[left] + ratio * (anchors[right] - anchors[left]))

    def word_at(recognized_pos: int) -> TimedWord:
        for char_start, char_end, word in word_ranges:
            if char_start <= recognized_pos < char_end:
                return word
        return word_ranges[-1][2]

    # Synthesized audio can have a breath or room tone before its first
    # syllable, so map the first expected character instead of assuming 0.0.
    starts = [word_at(map_expected_pos(0)).start]
    expected_cursor = 0
    for part in expected_parts[:-1]:
        expected_cursor += len(part)
        recognized_pos = map_expected_pos(expected_cursor)
        starts.append(word_at(recognized_pos).start)

    if any(b <= a for a, b in zip(starts, starts[1:])):
        logger.warning("[tts-align] 줄 시작 시각이 단조 증가하지 않음: %s", starts)
        return None
    return starts, confidence


def _load_model() -> object:
    global _MODEL
    if _MODEL is not None:
        return _MODEL
    with _MODEL_LOCK:
        if _MODEL is not None:
            return _MODEL
        # Must precede the faster_whisper/huggingface_hub import. `download_root`
        # alone does not redirect HF Xet's cache, which otherwise resolves to
        # an unwritable `/.cache` for the uid-1000 worker.
        configure_huggingface_cache()
        from faster_whisper import WhisperModel

        WHISPER_DOWNLOAD_ROOT.mkdir(parents=True, exist_ok=True)
        logger.info(
            "[tts-align] faster-whisper 로드: model=%s device=%s compute=%s",
            TTS_ALIGNMENT_MODEL,
            TTS_ALIGNMENT_DEVICE,
            TTS_ALIGNMENT_COMPUTE_TYPE,
        )
        _MODEL = WhisperModel(
            TTS_ALIGNMENT_MODEL,
            device=TTS_ALIGNMENT_DEVICE,
            compute_type=TTS_ALIGNMENT_COMPUTE_TYPE,
            download_root=str(WHISPER_DOWNLOAD_ROOT),
        )
    return _MODEL


def transcribe_tts_quality(audio_path: Path, expected_text: str = "") -> tuple[str, float | None]:
    """품질 게이트용 전사와 평균 단어 확률을 반환한다.

    ``align_narration_lines``와 동일한 lazy small/int8 모델 및 inference lock을
    공유한다. 호출자는 예외를 품질 ``inconclusive``으로 처리해야 하며, 이 함수는
    모델 로드/전사 실패를 음성 품질 실패로 바꾸지 않는다.
    """
    model = _load_model()
    with _INFERENCE_LOCK:
        segments, _info = model.transcribe(
            str(audio_path),
            language="ko",
            beam_size=3,
            vad_filter=False,
            word_timestamps=True,
            condition_on_previous_text=False,
            initial_prompt=expected_text,
        )
        words: list[TimedWord] = []
        for segment in segments:
            for word in segment.words or []:
                if not _compact(word.word):
                    continue
                words.append(TimedWord(
                    text=word.word,
                    start=float(word.start or 0.0),
                    end=float(word.end or 0.0),
                    probability=float(word.probability) if word.probability is not None else 0.0,
                ))
    if not words:
        raise RuntimeError("faster-whisper returned no timed words")
    probabilities = [word.probability for word in words]
    return " ".join(word.text for word in words), sum(probabilities) / len(probabilities)


def align_narration_lines(audio_path: Path, lines: list[str]) -> tuple[list[float], float] | None:
    """합성 음성을 전사하고 각 원문 줄의 실제 발화 시작 시각을 반환한다."""
    if len(lines) < 2:
        return ([0.0], 1.0) if lines else None

    try:
        model = _load_model()
        with _INFERENCE_LOCK:
            segments, _info = model.transcribe(
                str(audio_path),
                language="ko",
                beam_size=3,
                vad_filter=False,
                word_timestamps=True,
                condition_on_previous_text=True,
                initial_prompt=" ".join(lines),
            )
            timed_words: list[TimedWord] = []
            for segment in segments:
                for word in segment.words or []:
                    if word.start is None or word.end is None or not _compact(word.word):
                        continue
                    timed_words.append(TimedWord(
                        text=word.word,
                        start=float(word.start),
                        end=float(word.end),
                        probability=float(word.probability or 0.0),
                    ))
        result = align_words_to_lines(lines, timed_words)
        if result is not None:
            starts, confidence = result
            logger.info(
                "[tts-align] 실제 발화 정렬 완료: %d줄 confidence=%.3f",
                len(starts),
                confidence,
            )
        return result
    except Exception:
        logger.warning("[tts-align] faster-whisper 정렬 실패 — 무손상 비율 폴백", exc_info=True)
        return None
