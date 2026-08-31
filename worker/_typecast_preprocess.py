#!/usr/bin/env python3
"""Typecast TTS 데이터 전처리: 음량 정규화 + ASR 품질 검증."""

import argparse
import json
import logging
import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional
import difflib
import unicodedata

# config.settings를 faster_whisper import보다 먼저 해야 한다.
# 이 모듈이 import 시점에 HF_HOME/XDG_CACHE_HOME을 쓰기 가능한 경로로
# os.environ에 설정하는 부작용이 있다 — 생략하면 whisper가 기본 캐시 경로
# `/.cache`(root 소유)에 쓰려다 PermissionError로 조용히 실패한다.
import sys
sys.path.insert(0, str(Path(__file__).parent))
from config import settings as _cfg  # noqa: F401  (side effect: HF 캐시 경로 설정)

# faster-whisper 설정
try:
    from faster_whisper import WhisperModel
except ImportError:
    raise ImportError("faster-whisper 설치 필수: pip install faster-whisper")

# WaggleBot ai_worker.tts.quality 모듈 재사용
try:
    from ai_worker.tts.quality import normalize_quality_text
except (ImportError, ModuleNotFoundError):
    # 모듈 없으면 직접 구현
    def normalize_quality_text(text: str) -> str:
        """비교용 정규화."""
        text = unicodedata.normalize("NFD", text)
        text = text.encode("ascii", errors="ignore").decode("ascii")
        text = re.sub(r"[^0-9a-z가-힣]", "", text.lower())
        return text


@dataclass
class ClipQuality:
    """클립 품질 평가."""
    speaker: str
    clip_id: str  # e.g., "001"
    wav_path: str
    expected_text: str
    transcript: str
    cer: float  # Character Error Rate
    status: str  # "pass" or "fail"


def levenshtein_distance(s1: str, s2: str) -> int:
    """두 문자열 사이의 Levenshtein 거리 (삽입/삭제/치환 3-way DP)."""
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)

    prev_row = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = prev_row[j + 1] + 1
            deletions = curr_row[j] + 1
            substitutions = prev_row[j] + (c1 != c2)
            curr_row.append(min(insertions, deletions, substitutions))
        prev_row = curr_row
    return prev_row[-1]


def calculate_cer(expected: str, transcript: str) -> float:
    """Character Error Rate 계산 (0~1)."""
    expected_norm = normalize_quality_text(expected)
    transcript_norm = normalize_quality_text(transcript)
    
    if not expected_norm:
        return 0.0 if not transcript_norm else 1.0
    
    distance = levenshtein_distance(expected_norm, transcript_norm)
    return min(1.0, distance / len(expected_norm))


def normalize_audio_ffmpeg(input_wav: Path, output_wav: Path) -> bool:
    """ffmpeg의 loudnorm 필터로 음량 정규화."""
    try:
        cmd = [
            "ffmpeg", "-i", str(input_wav),
            "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
            "-ar", "44100", "-ac", "1", "-c:a", "pcm_s16le",
            "-y", str(output_wav)
        ]
        subprocess.run(cmd, capture_output=True, check=True, timeout=30)
        return True
    except Exception as e:
        logging.error(f"FFmpeg 정규화 실패 {input_wav}: {e}")
        return False


def load_whisper_model(model_name: str = "base", device: str = "cpu") -> WhisperModel:
    """faster-whisper 모델 로드."""
    logging.info(f"Whisper 모델 로드 중: {model_name} (device={device})")
    return WhisperModel(model_name, device=device, compute_type="int8")


def transcribe_audio(model: WhisperModel, wav_path: Path, language: str = "ko") -> str:
    """음성 파일을 Whisper로 전사."""
    try:
        segments, info = model.transcribe(str(wav_path), language=language, beam_size=5)
        transcript = " ".join(segment.text for segment in segments).strip()
        return transcript
    except Exception as e:
        logging.error(f"Whisper 전사 실패 {wav_path}: {e}")
        return ""


def preprocess_dataset(
    data_dir: Path,
    in_place: bool = False,
    whisper_model: Optional[WhisperModel] = None
) -> dict:
    """전체 데이터셋 전처리."""
    data_dir = Path(data_dir)
    if not data_dir.exists():
        raise FileNotFoundError(f"데이터 디렉토리 없음: {data_dir}")
    
    results = {
        "speakers": {},
        "total_clips": 0,
        "avg_cer": 0.0,
        "problem_clips": []
    }
    
    total_cer = 0.0
    clip_count = 0
    
    # 각 화자 폴더 순회
    for speaker_dir in sorted(data_dir.iterdir()):
        if not speaker_dir.is_dir():
            continue
        
        speaker = speaker_dir.name
        logging.info(f"화자 처리 중: {speaker}")
        
        speaker_clips = []
        speaker_cer_sum = 0.0
        
        # 각 클립 파일 처리
        for wav_file in sorted(speaker_dir.glob("*.wav")):
            lab_file = wav_file.with_suffix(".lab")
            
            if not lab_file.exists():
                logging.warning(f".lab 파일 없음: {wav_file}")
                continue
            
            clip_id = wav_file.stem
            
            # lab 파일에서 원문 읽기
            try:
                with open(lab_file, "r", encoding="utf-8") as f:
                    expected_text = f.read().strip()
            except Exception as e:
                logging.error(f"Lab 파일 읽기 실패 {lab_file}: {e}")
                continue
            
            # 음량 정규화
            if in_place:
                output_wav = wav_file
            else:
                # 임시 파일로 정규화 후 덮어쓰기
                temp_wav = wav_file.with_stem(f"{clip_id}_temp")
                if not normalize_audio_ffmpeg(wav_file, temp_wav):
                    logging.warning(f"정규화 건너뜀: {wav_file}")
                    continue
                temp_wav.replace(wav_file)
                output_wav = wav_file
            
            # Whisper 전사
            if whisper_model:
                transcript = transcribe_audio(whisper_model, output_wav)
            else:
                transcript = ""
            
            # CER 계산
            cer = calculate_cer(expected_text, transcript)
            status = "pass" if cer <= 0.15 else "fail"
            
            clip_quality = ClipQuality(
                speaker=speaker,
                clip_id=clip_id,
                wav_path=str(output_wav),
                expected_text=expected_text,
                transcript=transcript,
                cer=cer,
                status=status
            )
            
            speaker_clips.append(clip_quality)
            speaker_cer_sum += cer
            total_cer += cer
            clip_count += 1
            
            if status == "fail":
                results["problem_clips"].append({
                    "speaker": speaker,
                    "clip_id": clip_id,
                    "cer": cer,
                    "expected": expected_text[:50],
                    "transcript": transcript[:50]
                })
            
            logging.info(f"  {clip_id}: CER={cer:.4f} ({status})")
        
        if speaker_clips:
            avg_speaker_cer = speaker_cer_sum / len(speaker_clips)
            results["speakers"][speaker] = {
                "clip_count": len(speaker_clips),
                "avg_cer": avg_speaker_cer,
                "clips": [asdict(c) for c in speaker_clips]
            }
    
    results["total_clips"] = clip_count
    if clip_count > 0:
        results["avg_cer"] = total_cer / clip_count
    
    return results


def main():
    parser = argparse.ArgumentParser(
        description="Typecast TTS 데이터 전처리: 음량 정규화 + ASR 검증"
    )
    parser.add_argument("--data-dir", default="data-finetune", help="데이터 디렉토리")
    parser.add_argument("--in-place", action="store_true", help="원본 파일 덮어쓰기")
    parser.add_argument("--whisper-model", default="large-v3", help="Whisper 모델 — 프로젝트 표준(config.settings.WHISPER_MODEL)과 통일")
    parser.add_argument("--device", default="cpu", help="Whisper 장치 (cpu, cuda)")
    parser.add_argument("--log-level", default="INFO", help="로그 레벨")
    
    args = parser.parse_args()
    
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s - %(levelname)s - %(message)s"
    )
    
    data_dir = Path(args.data_dir)
    logging.info(f"전처리 시작: {data_dir} (in_place={args.in_place})")
    
    # Whisper 모델 로드 — 실패 시 즉시 중단 (조용히 빈 전사로 넘어가면
    # 모든 클립이 CER=1.0으로 위장 실패하는 사고가 난다, 실제로 발생했었음)
    whisper_model = load_whisper_model(args.whisper_model, args.device)
    
    # 전처리 실행
    results = preprocess_dataset(data_dir, in_place=args.in_place, whisper_model=whisper_model)
    
    # 결과 저장
    report_file = data_dir / "preprocess_report.json"
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    logging.info(f"결과 저장: {report_file}")
    
    # 요약 출력
    print(f"\n{'='*60}")
    print(f"전처리 완료 (데이터: {data_dir})")
    print(f"{'='*60}")
    print(f"총 클립 수: {results['total_clips']}")
    print(f"평균 CER: {results['avg_cer']:.4f}")
    print(f"문제 클립 수 (CER > 0.15): {len(results['problem_clips'])}")
    
    if results["problem_clips"]:
        print(f"\n문제 클립 목록:")
        for clip in results["problem_clips"][:10]:  # 처음 10개만 표시
            print(f"  - {clip['speaker']}/{clip['clip_id']}: CER={clip['cer']:.4f}")
        if len(results["problem_clips"]) > 10:
            print(f"  ... 외 {len(results['problem_clips']) - 10}개")
    
    print(f"\n화자별 요약:")
    for speaker, speaker_data in results["speakers"].items():
        print(f"  {speaker}: {speaker_data['clip_count']}개, 평균 CER={speaker_data['avg_cer']:.4f}")


if __name__ == "__main__":
    main()
