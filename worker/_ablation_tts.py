#!/usr/bin/env python3
"""독립 실행 TTS Ablation 스크립트 — 오디오 품질 인자 측정용.

loudnorm / atempo / sentence-pause / 발음사전 등의 변형을 테스트 가능하게 설계.
기존 fish_client의 내부 함수들(_voice_params, _base_payload, 등)을 재사용해서
파이프라인 일관성 유지. 공유 설정 파일은 수정하지 않음.
"""

import argparse
import asyncio
import logging
import re
import subprocess
import sys
import shutil
import tempfile
import textwrap
from pathlib import Path

# worker 디렉토리를 sys.path에 추가 (ai_worker import 가능하게)
_SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(_SCRIPT_DIR))

# 부모 디렉토리도 추가 (config import용)
_REPO_DIR = _SCRIPT_DIR.parent
sys.path.insert(0, str(_REPO_DIR))

import httpx

from ai_worker.tts.fish_client import (
    _HTTP_TIMEOUT,
    _base_payload,
    _concat_wavs,
    _resolve_references,
    _split_text,
    _synthesize_segment,
    _voice_params,
)
from ai_worker.tts.normalizer import normalize_for_tts

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
# 기본 텍스트 (카놀라유 사연 496자)
# ──────────────────────────────────────────────────────────────
DEFAULT_TEXT = """카놀라유 하나로 신혼이 뒤집혔어요.

신혼 1년 됐을 때예요 남편 고모님이 오셨거든요.

7년 만에 한국에 오신 분이라 어머니 같은 분이래요.

다섯 분이 저희 집에 오셔서 기쁜 마음으로 준비했어요.

재료가 한우 한돈 해산물까지 30만원이 넘었거든요.

전도 엄청 부쳐야 해서 기름이 두 통이나 필요했는데,

올리브오일은 한 통에 38,000원 현실적으로 두 통을 써요?

선물로 들어온 카놀라유 썼는데 이게 문제가 될 줄이야.

남편이 주방에서 갑자기 기름이 왜 이거냐는 거예요.

티 나는 데만 좋은 거 쓰고 티 안 나면 야박하다고,

기가 막혀 할 말이 없었더니 남편이 이러는 거예요.

거봐 할말없지.

그냥 말없이 저녁 상 차렸어요.

근데 고모님 봉투가 문제였어요.

고모님이 수고했다며 봉투를 내미시는데,

남편이 낚아챘어요.

고모님한테 도로 밀어넣더니 저한테 하는 말이.

받을 자격 없는 것 같다.

기름 트집 잡고 봉투까지 빼앗는 거잖아요.

지금도 냉전 중이에요."""

# ──────────────────────────────────────────────────────────────
# Loudnorm 정책별 ffmpeg 필터 파라미터
# ──────────────────────────────────────────────────────────────
LOUDNORM_CONFIGS = {
    "off": None,
    "single": "loudnorm=I=-16:TP=-1.5:LRA=11",
    "relaxed": "loudnorm=I=-16:TP=-1.5:LRA=16",
}


def load_text_input(text_file: str | None) -> str:
    """입력 텍스트 로드: 파일 또는 기본값."""
    if text_file:
        p = Path(text_file)
        if not p.exists():
            raise FileNotFoundError(f"텍스트 파일 없음: {text_file}")
        return p.read_text(encoding="utf-8").strip()
    return DEFAULT_TEXT.strip()


def apply_pronunciation_dict(text: str, enabled: bool) -> str:
    """발음 교정 사전 적용 여부 제어.
    
    현재 normalize_for_tts는 발음사전을 비활성화하고 있으므로,
    enabled=True일 때만 _PRONUNCIATION_MAP_BUILTIN을 직접 적용한다.
    """
    if not enabled:
        # 발음사전 미적용 — 현재 기본값
        return text
    
    # 발음사전 직접 적용 (normalizer.py의 _PRONUNCIATION_MAP_BUILTIN)
    pronunciation_map = {
        "댓글": "대끌",
        "맛집": "마찝",
        "꽃길": "꼳낄",
        "숫자": "숟짜",
        "곗곗": "곧꼳",
        "낱개": "나깨",
        "갯벌": "개뻘",
        "웃기": "욷끼",
        "있다": "읻따",
        "없다": "업따",
        "있고": "읻꼬",
        "없고": "업꼬",
        "있는": "인는",
        "없는": "엄는",
        "있습니다": "읻씀니다",
        "없습니다": "업씀니다",
        "있었": "이썯",
        "없었": "업썯",
        "했습니다": "해씀니다",
        "됐습니다": "돼씀니다",
        "작년": "장년",
        "국내": "궁내",
        "국민": "궁민",
        "학년": "항년",
        "합니다": "함니다",
        "십만": "심만",
        "백만": "뱅만",
        "관련": "괄련",
        "연락": "열락",
        "같이": "가치",
        "굳이": "구지",
        "붙이": "부치",
        "좋아": "조아",
        "좋은": "조은",
        "좋다": "조타",
        "놓다": "노타",
        "넣다": "너타",
        "않다": "안타",
        "않은": "아는",
        "않아": "아나",
        "많다": "만타",
        "많은": "마는",
        "많이": "마니",
        "괜찮": "괜찬",
        "읽다": "익따",
        "읽고": "익꼬",
        "읽는": "잉는",
        "삶": "삼",
        "젊은": "절문",
        "밟다": "밥따",
        "높이": "노피",
    }
    result = text
    for original, phonetic in pronunciation_map.items():
        result = result.replace(original, phonetic)
    return result


def post_process_audio_custom(
    path: Path,
    speed: float = 1.0,
    loudnorm_policy: str = "single",
    trim_prefix_secs: float = 0.0,
) -> None:
    """커스텀 FFmpeg 후처리: atempo / loudnorm을 인자로 제어.
    
    출력은 항상 44100Hz mono pcm_s16le로 정규화.
    loudnorm_policy가 "off"면 loudnorm 필터를 안 씀.
    """
    tmp = path.with_name(path.stem + "_proc.wav")
    filters: list[str] = []
    
    if trim_prefix_secs > 0:
        filters.append(f"atrim=start={trim_prefix_secs:.3f},asetpts=PTS-STARTPTS")
    
    # loudnorm 필터 선택
    loudnorm_param = LOUDNORM_CONFIGS.get(loudnorm_policy)
    if loudnorm_param:
        filters.append(loudnorm_param)
    
    # atempo (배속)
    if abs(speed - 1.0) > 1e-3:
        filters.append(f"atempo={speed}")
    
    af_chain = ",".join(filters)
    try:
        cmd = [
            "ffmpeg", "-y", "-i", str(path),
        ]
        if af_chain:
            cmd.extend(["-af", af_chain])
        cmd.extend([
            "-ar", "44100", "-ac", "1", "-c:a", "pcm_s16le",
            str(tmp),
        ])
        result = subprocess.run(cmd, capture_output=True, timeout=60)
        if result.returncode == 0 and tmp.exists() and tmp.stat().st_size > 0:
            tmp.replace(path)
            logger.debug(
                "오디오 후처리 완료 (loudnorm=%s, speed=%.2f): %s",
                loudnorm_policy, speed, path.name,
            )
        else:
            logger.warning(
                "오디오 후처리 실패 (rc=%d): %s",
                result.returncode,
                result.stderr[-200:].decode(errors="replace") if result.stderr else "",
            )
    except FileNotFoundError:
        logger.debug("ffmpeg 미설치 — 오디오 후처리 건너뜀")
    except Exception as exc:
        logger.warning("오디오 후처리 오류: %s", exc)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)


def create_silence_wav(duration_ms: int, sample_rate: int = 44100) -> bytes:
    """지정된 길이(ms)의 무음 WAV 생성 (ffmpeg anullsrc 사용).
    
    임시 WAV로 생성 후 bytes로 읽어서 반환.
    """
    if duration_ms <= 0:
        return b""
    
    duration_sec = duration_ms / 1000.0
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_path = tmp.name
    
    try:
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", f"anullsrc=r={sample_rate}:cl=mono",
            "-t", f"{duration_sec}",
            "-c:a", "pcm_s16le",
            tmp_path,
        ]
        subprocess.run(cmd, capture_output=True, timeout=30, check=True)
        return Path(tmp_path).read_bytes()
    finally:
        Path(tmp_path).unlink(missing_ok=True)


async def run_synthesis(
    voice: str,
    text: str,
    speed: float,
    loudnorm_policy: str,
    sentence_pause_ms: int,
    pronun_dict_enabled: bool,
    output_path: Path,
) -> None:
    """메인 합성 루프: 텍스트 분할 → 세그먼트별 합성 → concat → 후처리."""
    
    # 발음사전 적용 여부
    if pronun_dict_enabled:
        text = apply_pronunciation_dict(text, enabled=True)
    
    # 정규화 (발음사전은 normalizer에서 비활성화되어 있음)
    text = normalize_for_tts(text)
    
    # 텍스트 분할
    max_chars = 200  # fish_client의 TTS_MAX_CHARS_PER_REQUEST 참고
    segments = _split_text(text, max_chars)
    
    if not segments:
        raise ValueError("입력 텍스트가 비어있음")
    
    logger.info("합성 시작: %d 세그먼트, 음성=%s, 속도=%.2f, loudnorm=%s, pause=%dms",
                len(segments), voice, speed, loudnorm_policy, sentence_pause_ms)
    
    # 참조 오디오 로드
    ref_fragment = _resolve_references(voice)
    params = _voice_params(voice)
    base_payload = _base_payload(ref_fragment, params)
    
    # 임시 디렉토리에서 세그먼트 생성
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        seg_files: list[Path] = []
        
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            for i, segment in enumerate(segments):
                seg_file = tmpdir_path / f"segment_{i:03d}.wav"
                logger.info("세그먼트 %d/%d 합성 중...", i + 1, len(segments))
                
                # 기존 _synthesize_segment 재사용 (실제 시그니처에 맞춤)
                audio_bytes, _spc = await _synthesize_segment(
                    client,
                    segment,
                    len(segment),
                    base_payload,
                    voice_key=voice,
                    expected_text=segment,
                )
                seg_file.write_bytes(audio_bytes)
                seg_files.append(seg_file)
        
        # Concat (무음 삽입 포함)
        if sentence_pause_ms > 0:
            # 무음을 삽입한 concat 파일 작성
            concat_file = tmpdir_path / "concat_with_pauses.txt"
            concat_lines: list[str] = []
            
            silence_wav = create_silence_wav(sentence_pause_ms)
            silence_file = None
            if silence_wav:
                silence_file = tmpdir_path / "silence.wav"
                silence_file.write_bytes(silence_wav)
            
            for i, seg_file in enumerate(seg_files):
                concat_lines.append(f"file '{seg_file.resolve()}'")
                if i < len(seg_files) - 1 and silence_file:
                    # 마지막 세그먼트 이후는 무음 삽입 안 함
                    concat_lines.append(f"file '{silence_file.resolve()}'")
            
            concat_file.write_text("\n".join(concat_lines), encoding="utf-8")
            
            # FFmpeg concat demuxer로 병합
            tmp_concat = tmpdir_path / "concat_output.wav"
            subprocess.run(
                [
                    "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                    "-i", str(concat_file), "-c", "copy", str(tmp_concat),
                ],
                capture_output=True, check=True, timeout=120,
            )
            shutil.move(str(tmp_concat), str(output_path))
        else:
            # 일반 concat (무음 없음)
            _concat_wavs(seg_files, output_path)
    
    # 후처리
    post_process_audio_custom(
        output_path,
        speed=speed,
        loudnorm_policy=loudnorm_policy,
    )
    
    logger.info("합성 완료: %s", output_path)


def main():
    parser = argparse.ArgumentParser(
        description="WaggleBot TTS Ablation 테스트 스크립트",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""
        Examples:
          python3 _ablation_tts.py --voice manbo --speed 1.0 --loudnorm single \\
            --sentence-pause-ms 300 --pronun-dict on --out test.wav
          
          python3 _ablation_tts.py --text-file my_text.txt --speed 1.1 \\
            --loudnorm relaxed --out /tmp/ablation_result.wav
        """),
    )
    
    parser.add_argument("--voice", default="manbo",
                        help="voice key (default: manbo)")
    parser.add_argument("--text-file", default=None,
                        help="text file path (if omitted, use default)")
    parser.add_argument("--speed", type=float, default=1.0,
                        help="playback speed/atempo (default: 1.0)")
    parser.add_argument("--loudnorm", choices=["off", "single", "relaxed"],
                        default="single",
                        help="loudnorm policy (default: single)")
    parser.add_argument("--sentence-pause-ms", type=int, default=0,
                        help="silence between segments in ms (default: 0, none)")
    parser.add_argument("--pronun-dict", choices=["on", "off"], default="on",
                        help="apply pronunciation dictionary (default: on, currently disabled)")
    parser.add_argument("--out", required=True,
                        help="output WAV path")
    
    args = parser.parse_args()
    
    # 로깅 설정
    logging.basicConfig(
        level=logging.INFO,
        format="[%(levelname)s] %(message)s",
    )
    
    # 입력 검증
    output_path = Path(args.out)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        text = load_text_input(args.text_file)
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    
    # 사용 설정 요약 출력
    config_summary = (
        f"voice={args.voice} text_len={len(text)} speed={args.speed} "
        f"loudnorm={args.loudnorm} pause_ms={args.sentence_pause_ms} "
        f"pronun_dict={args.pronun_dict}"
    )
    print(f"Config: {config_summary}")
    
    # 비동기 실행
    try:
        asyncio.run(run_synthesis(
            voice=args.voice,
            text=text,
            speed=args.speed,
            loudnorm_policy=args.loudnorm,
            sentence_pause_ms=args.sentence_pause_ms,
            pronun_dict_enabled=(args.pronun_dict == "on"),
            output_path=output_path,
        ))
    except Exception as exc:
        logger.error("Synthesis failed: %s", exc, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
