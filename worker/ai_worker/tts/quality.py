"""TTS 합성 품질 판정 도우미.

Fish Speech 호출과 faster-whisper 모델 로딩은 이 모듈의 책임이 아니다.  합성기는
저비용 검사(길이, 분할)를 먼저 수행하고, 이 모듈은 긴 후보에 한해 주입된 ASR
전사 함수로 결과를 확인한다.  따라서 짧은 카피나 이미 명백히 길이 검증에 실패한
오디오 때문에 CPU Whisper를 불필요하게 실행하지 않는다.
"""

from __future__ import annotations

import difflib
import hashlib
import logging
import re
import unicodedata
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path


_COMPACT_RE = re.compile(r"[^0-9a-z가-힣]+")
_WORD_RE = re.compile(r"[0-9A-Za-z가-힣]+")
_HANGUL_RE = re.compile(r"[가-힣]")
logger = logging.getLogger(__name__)

# ASR은 고유명사·표기 차이를 낼 수 있다. 짧은 문구에 장문과 같은 기준을 적용하면
# 정상 음성을 과도하게 재합성하므로 별도 완화 기준을 둔다.
DEFAULT_MIN_CHARS_FOR_ASR = 8
DEFAULT_SHORT_TEXT_CHARS = 14
DEFAULT_MIN_SIMILARITY = 0.78
DEFAULT_SHORT_MIN_SIMILARITY = 0.60
DEFAULT_MIN_ASR_CONFIDENCE = 0.45
DEFAULT_MIN_WORD_COVERAGE = 0.72
# A low ASR confidence normally means that the recognizer is not reliable
# enough to blame the TTS candidate.  It must not, however, hide a transcript
# that is demonstrably unrelated to a long expected segment.  These are
# deliberately much weaker than the normal pass thresholds: they only turn a
# near-total mismatch into a retry, not ordinary ASR wording variation.
DEFAULT_CATASTROPHIC_SIMILARITY = 0.35
DEFAULT_CATASTROPHIC_WORD_COVERAGE = 0.25
# Fish Speech occasionally inserts non-script speech (often foreign-language
# bleed that Korean ASR renders as plausible Hangul). Similarity/coverage only
# measure expected-text recall, so pure insertions can still "pass". Reject
# contiguous Hangul inserts that are not substrings of the expected script.
DEFAULT_UNEXPECTED_INSERT_MIN_CHARS = 3


@dataclass(frozen=True)
class BoundaryIssue:
    """한국어 어절 내부에서 발견한 위험한 분할 위치."""

    offset: int
    left_context: str
    right_context: str


@dataclass(frozen=True)
class SegmentBoundaryReport:
    """TTS 요청 세그먼트 경계의 사전 검증 결과."""

    valid: bool
    checked_boundaries: int
    unsafe_boundaries: tuple[BoundaryIssue, ...] = ()
    indeterminate_boundaries: int = 0


@dataclass(frozen=True)
class TranscriptQuality:
    """원문과 ASR 전사의 비교 결과.

    ``requires_retry``가 참인 경우만 합성 후보를 다시 만들어야 한다. ASR 자체의
    confidence가 낮은 경우는 음성 불량으로 단정하지 않고 ``inconclusive``으로 둔다.
    """

    expected: str
    transcript: str
    similarity: float
    word_coverage: float | None
    missing_fragments: tuple[str, ...]
    status: str
    requires_retry: bool
    reason: str


@dataclass(frozen=True)
class RetryDecision:
    """현재 후보의 품질 결과에 따른 다음 Fish Speech seed 결정."""

    attempt: int
    seed: int
    retry: bool
    retries_remaining: int
    reason: str


def normalize_quality_text(text: str) -> str:
    """비교용으로만 유니코드·대소문자·문장부호를 정규화한다.

    발음 사전이나 숫자 읽기 변환은 하지 않는다. 호출자는 TTS에 실제로 보낸
    정규화 텍스트를 ``expected_text``로 전달해야 한다.
    """
    normalized = unicodedata.normalize("NFKC", text or "").lower()
    return _COMPACT_RE.sub("", normalized)


def _word_tokens(text: str) -> list[str]:
    return [match.group(0).lower() for match in _WORD_RE.finditer(unicodedata.normalize("NFKC", text or ""))]


def _missing_fragments(expected: str, transcript: str, *, minimum_length: int = 2) -> tuple[str, ...]:
    """ASR 결과에서 사라진 의미 있는 원문 조각만 반환한다."""
    matcher = difflib.SequenceMatcher(None, expected, transcript, autojunk=False)
    fragments: list[str] = []
    for tag, expected_start, expected_end, _actual_start, _actual_end in matcher.get_opcodes():
        if tag not in {"delete", "replace"}:
            continue
        fragment = expected[expected_start:expected_end]
        if len(fragment) >= minimum_length:
            fragments.append(fragment)
    return tuple(fragments)


def _word_coverage(expected_text: str, transcript_text: str) -> float | None:
    """공백을 신뢰할 수 있을 때만 어절 LCS 비율을 계산한다."""
    expected_words = _word_tokens(expected_text)
    transcript_words = _word_tokens(transcript_text)
    # 공백 없는 ASR 전사는 문자 유사도로 충분히 판정한다. 이 경우 token LCS를
    # 강제하면 정상 전사를 전부 하나의 단어 누락으로 오인한다.
    if len(expected_words) < 2 or len(transcript_words) < 2:
        return None

    matcher = difflib.SequenceMatcher(None, expected_words, transcript_words, autojunk=False)
    matched = sum(block.size for block in matcher.get_matching_blocks())
    return matched / len(expected_words)


def _missing_words(expected_text: str, transcript_text: str) -> tuple[str, ...]:
    """공백이 있는 ASR 전사에서 통째로 누락된 어절을 찾는다."""
    expected_words = _word_tokens(expected_text)
    transcript_words = _word_tokens(transcript_text)
    if len(expected_words) < 2 or len(transcript_words) < 2:
        return ()
    matcher = difflib.SequenceMatcher(None, expected_words, transcript_words, autojunk=False)
    missing: list[str] = []
    for tag, start, end, _actual_start, _actual_end in matcher.get_opcodes():
        if tag in {"delete", "replace"}:
            missing.extend(expected_words[start:end])
    return tuple(missing)



def _hangul_only(text: str) -> str:
    """Quality-insert detection uses Hangul only — Latin ASR junk is ignored."""
    return "".join(ch for ch in unicodedata.normalize("NFKC", text or "") if "가" <= ch <= "힣")


def unexpected_hangul_inserts(
    expected_text: str,
    transcript: str,
    *,
    min_chars: int = DEFAULT_UNEXPECTED_INSERT_MIN_CHARS,
) -> tuple[str, ...]:
    """Return Hangul inserts in the transcript that are absent from the script.

    Used to catch TTS language-bleed / hallucination between valid phrases.
    Fragments that already appear in the expected text (duplication, reorder)
    are ignored so ordinary ASR restatement does not force a retry.
    Latin/English ASR debris is stripped first so it cannot fake an insert.
    """
    expected = _hangul_only(expected_text)
    actual = _hangul_only(transcript)
    if not expected or not actual:
        return ()
    matcher = difflib.SequenceMatcher(None, expected, actual, autojunk=False)
    inserts: list[str] = []
    for tag, _i1, _i2, j1, j2 in matcher.get_opcodes():
        if tag not in {"insert", "replace"}:
            continue
        fragment = actual[j1:j2]
        if len(fragment) < min_chars:
            continue
        if fragment in expected:
            continue
        inserts.append(fragment)
    return tuple(dict.fromkeys(inserts))


def assess_transcript(
    expected_text: str,
    transcript: str,
    *,
    asr_confidence: float | None = None,
    min_similarity: float = DEFAULT_MIN_SIMILARITY,
    short_min_similarity: float = DEFAULT_SHORT_MIN_SIMILARITY,
    short_text_chars: int = DEFAULT_SHORT_TEXT_CHARS,
    min_asr_confidence: float = DEFAULT_MIN_ASR_CONFIDENCE,
    min_word_coverage: float = DEFAULT_MIN_WORD_COVERAGE,
) -> TranscriptQuality:
    """정규화된 예상 대사와 ASR 전사의 유사도·누락을 판정한다."""
    expected = normalize_quality_text(expected_text)
    actual = normalize_quality_text(transcript)
    if not expected:
        return TranscriptQuality(expected, actual, 1.0, None, (), "skipped", False, "empty_expected")
    if not actual:
        return TranscriptQuality(expected, actual, 0.0, 0.0, (expected,), "failed", True, "empty_transcript")

    matcher = difflib.SequenceMatcher(None, expected, actual, autojunk=False)
    similarity = sum(block.size for block in matcher.get_matching_blocks()) / len(expected)
    # Whisper frequently merges or splits Korean eojeols.  If the compact text
    # matches exactly, that segmentation difference is not a missing-word TTS
    # failure and must not trigger an expensive re-synthesis.
    coverage = 1.0 if expected == actual else _word_coverage(expected_text, transcript)
    missing = _missing_fragments(expected, actual)
    word_missing = () if expected == actual else _missing_words(expected_text, transcript)
    if word_missing:
        missing = tuple(dict.fromkeys((*missing, *word_missing)))

    threshold = short_min_similarity if len(expected) < short_text_chars else min_similarity
    similarity_failed = similarity < threshold
    coverage_failed = coverage is not None and coverage < min_word_coverage
    unexpected_inserts = unexpected_hangul_inserts(expected_text, transcript)
    if unexpected_inserts:
        missing = tuple(dict.fromkeys((*missing, *unexpected_inserts)))

    # 낮은 전사 confidence는 보통 TTS 결함의 증거가 아니다. 다만 충분히 긴
    # 기대 대사와 거의 무관한 전사가 동시에 나오면, 불확정으로 통과시킬 경우
    # 실제 누락 후보가 재합성 없이 배포된다. 이 경우만 정상 실패 경로로 보낸다.
    catastrophic_mismatch = (
        len(expected) >= short_text_chars
        and similarity < DEFAULT_CATASTROPHIC_SIMILARITY
        and coverage is not None
        and coverage < DEFAULT_CATASTROPHIC_WORD_COVERAGE
    )
    # Script-absent Hangul inserts are positive evidence of TTS bleed, not ASR
    # uncertainty — do not downgrade them to inconclusive on low confidence.
    if unexpected_inserts:
        return TranscriptQuality(
            expected,
            actual,
            similarity,
            coverage,
            missing,
            "failed",
            True,
            "unexpected_speech_insert",
        )
    if (
        asr_confidence is not None
        and asr_confidence < min_asr_confidence
        and not catastrophic_mismatch
    ):
        return TranscriptQuality(expected, actual, similarity, coverage, missing, "inconclusive", False, "low_asr_confidence")

    if similarity_failed:
        return TranscriptQuality(expected, actual, similarity, coverage, missing, "failed", True, "low_similarity")
    if coverage_failed:
        return TranscriptQuality(expected, actual, similarity, coverage, missing, "failed", True, "missing_word")
    return TranscriptQuality(expected, actual, similarity, coverage, missing, "passed", False, "matched")


def should_run_asr_quality_check(
    expected_text: str,
    *,
    duration_seconds: float | None = None,
    min_chars: int = DEFAULT_MIN_CHARS_FOR_ASR,
    min_seconds_per_char: float = 0.05,
    max_seconds_per_char: float = 0.35,
) -> bool:
    """CPU ASR가 실제로 유용한 후보인지 반환한다.

    길이 비율이 이미 비정상이면 기존의 저비용 길이 재시도가 처리해야 하므로 ASR를
    호출하지 않는다.  매우 짧은 카피는 전사 편차가 커서 품질 게이트에서 제외한다.
    """
    expected = normalize_quality_text(expected_text)
    if len(expected) < min_chars:
        return False
    if duration_seconds is None:
        return True
    seconds_per_char = duration_seconds / len(expected)
    return min_seconds_per_char <= seconds_per_char <= max_seconds_per_char


def assess_audio_with_asr(
    expected_text: str,
    audio_path: Path | None,
    transcribe: Callable[[Path], tuple[str, float | None]],
    *,
    duration_seconds: float | None = None,
) -> TranscriptQuality:
    """필요한 경우에만 주입된 CPU ASR를 호출해 합성 후보를 판정한다.

    ``transcribe``는 ``(전사문, 평균 confidence 또는 None)``을 반환한다. 모델
    로딩과 캐시는 호출자가 소유하므로 alignment의 지연 로드 모델을 재사용할 수 있다.
    ASR가 필요한데 오디오 경로가 없으면 품질 결함으로 단정하지 않고 불확정 처리한다.
    """
    if not should_run_asr_quality_check(expected_text, duration_seconds=duration_seconds):
        expected = normalize_quality_text(expected_text)
        return TranscriptQuality(expected, "", 1.0, None, (), "skipped", False, "asr_not_needed")
    if audio_path is None:
        expected = normalize_quality_text(expected_text)
        return TranscriptQuality(expected, "", 1.0, None, (), "inconclusive", False, "asr_unavailable")
    try:
        transcript, confidence = transcribe(audio_path)
    except Exception:
        # Whisper 모델 로드/추론 오류는 합성 오디오의 결함과 구분할 수 없다. 품질
        # 재생성 루프를 증폭시키지 않고 이 후보를 정상 경로로 넘긴다.
        logger.warning("[tts-quality] ASR 품질 검사 불가 — 후보 수용", exc_info=True)
        expected = normalize_quality_text(expected_text)
        return TranscriptQuality(expected, "", 1.0, None, (), "inconclusive", False, "asr_unavailable")
    return assess_transcript(expected_text, transcript, asr_confidence=confidence)


def candidate_seed(voice_key: str, text: str, attempt: int = 0) -> int:
    """voice·대사·후보 번호에서 재현 가능한 32-bit Fish Speech seed를 만든다."""
    if attempt < 0:
        raise ValueError("attempt must be >= 0")
    source = f"{voice_key}\0{normalize_quality_text(text)}\0{attempt}".encode("utf-8")
    value = int.from_bytes(hashlib.blake2s(source, digest_size=4).digest(), "big")
    return value or 1


def quality_retry_decision(
    quality: TranscriptQuality,
    *,
    voice_key: str,
    text: str,
    attempt: int,
    max_retries: int = 2,
) -> RetryDecision:
    """최대 두 번의 품질 재합성 정책과 다음 후보 seed를 반환한다."""
    if attempt < 0:
        raise ValueError("attempt must be >= 0")
    if max_retries < 0:
        raise ValueError("max_retries must be >= 0")
    retries_remaining = max(max_retries - attempt, 0)
    retry = quality.requires_retry and retries_remaining > 0
    next_attempt = attempt + 1 if retry else attempt
    return RetryDecision(
        attempt=next_attempt,
        seed=candidate_seed(voice_key, text, next_attempt),
        retry=retry,
        retries_remaining=max(max_retries - next_attempt, 0) if retry else retries_remaining,
        reason=quality.reason,
    )


def validate_korean_segment_boundaries(text: str, boundaries: Sequence[int]) -> SegmentBoundaryReport:
    """원문 offset들이 한국어 어절 중간을 자르는지 검사한다."""
    issues: list[BoundaryIssue] = []
    valid_boundaries = 0
    for offset in boundaries:
        if not 0 < offset < len(text):
            continue
        valid_boundaries += 1
        left, right = text[offset - 1], text[offset]
        if not (_HANGUL_RE.fullmatch(left) and _HANGUL_RE.fullmatch(right)):
            continue
        issues.append(BoundaryIssue(
            offset=offset,
            left_context=text[max(0, offset - 8):offset],
            right_context=text[offset:min(len(text), offset + 8)],
        ))
    return SegmentBoundaryReport(not issues, valid_boundaries, tuple(issues))


def validate_segment_boundaries(
    segments: Sequence[str],
    *,
    source_text: str | None = None,
) -> SegmentBoundaryReport:
    """세그먼트 배열을 원문 기준으로 검사한다.

    ``source_text``를 넘기면 세그먼트 양끝에서 제거된 공백도 복원해 판단하므로,
    합성 직전 ``strip()``된 배열에도 안전하다. 원문을 알 수 없고 문자열이 재조합되지
    않으면 오탐 방지를 위해 해당 경계는 ``indeterminate``로 보고 통과시킨다.
    """
    if len(segments) < 2:
        return SegmentBoundaryReport(True, 0)

    source = source_text if source_text is not None else "".join(segments)
    cursor = 0
    boundaries: list[int] = []
    indeterminate = 0
    for segment in segments[:-1]:
        if not segment:
            indeterminate += 1
            continue
        index = source.find(segment, cursor)
        if index < 0:
            indeterminate += 1
            continue
        cursor = index + len(segment)
        boundaries.append(cursor)

    report = validate_korean_segment_boundaries(source, boundaries)
    return SegmentBoundaryReport(
        report.valid,
        report.checked_boundaries,
        report.unsafe_boundaries,
        indeterminate,
    )
