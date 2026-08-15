#!/usr/bin/env python3
"""LoRA 평가 스크립트 — TTS 합성 및 오디오 측정.

텍스트 2개 (카놀라유 + 새 사연)로 각각 3종 설정(현행85%, LoRA, 원본)으로 합성.
_ablation_tts.py의 run_synthesis를 재사용하고, _measure_tts.py로 측정.
"""

import argparse
import sys
import textwrap
from pathlib import Path

# DEFAULT_TEXT (from _ablation_tts.py)
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

# 새 사연 (corpus_chunks.json 없으므로 하드코딩)
NEW_STORY_TEXT = """연애 9년, 결혼 반년인데 남편이 갑자기 외로워한다고 했어요.

더 자주 만나고 싶다, 더 시간을 써달라고요.

저는 일도 많고 피곤한데 남편은 저한테만 집중해줄 걸 바라고 있었어요.

아이도 없는데 왜 이렇게 외로워하는지 이해가 안 돼요.

남편 친구들은 다들 부부가 떨어져 있는데도 잘 지낸다더니요.

남편이 너무 의존적인 건 아닐까 싶기도 해요."""


class EvaluationPlan:
    """평가 계획 및 생성할 파일 목록."""
    
    def __init__(self, out_dir: Path, checkpoint_label: str):
        self.out_dir = out_dir
        self.checkpoint_label = checkpoint_label
        self.out_dir.mkdir(parents=True, exist_ok=True)
        
        # 생성할 파일들 (이름 규칙: {text_id}_{variant}.wav)
        self.files = {
            "kanola": {
                "현행85": {
                    "voice": "typecast_ref",
                    "text": DEFAULT_TEXT,
                    "settings": {"speed": 1.0, "loudnorm": "relaxed", "pause_ms": 300},
                },
                "LoRA": {
                    "voice": "typecast_ref",  # LoRA로 전환될 것 가정
                    "text": DEFAULT_TEXT,
                    "settings": {"speed": 1.0, "loudnorm": "relaxed", "pause_ms": 300},
                    "note": "fish-speech가 LoRA 체크포인트로 전환된 상태 가정"
                },
                "원본": {
                    "type": "copy_reference",
                    "note": "typecast_kanola.wav 복사"
                },
            },
            "newstory": {
                "현행85": {
                    "voice": "typecast_ref",
                    "text": NEW_STORY_TEXT,
                    "settings": {"speed": 1.0, "loudnorm": "relaxed", "pause_ms": 300},
                },
                "LoRA": {
                    "voice": "typecast_ref",
                    "text": NEW_STORY_TEXT,
                    "settings": {"speed": 1.0, "loudnorm": "relaxed", "pause_ms": 300},
                    "note": "fish-speech가 LoRA 체크포인트로 전환된 상태 가정"
                },
                # newstory는 원본 생략
            }
        }
    
    def count_synthesis_tasks(self) -> int:
        """실제 합성 작업 수 (원본 복사·생략 제외)."""
        count = 0
        for text_id, variants in self.files.items():
            for variant, config in variants.items():
                if config.get("type") != "copy_reference":
                    count += 1
        return count
    
    def get_output_path(self, text_id: str, variant: str) -> Path:
        """출력 파일 경로."""
        # 파일명: {text_id}_{variant}.wav
        filename = f"{text_id}_{variant}.wav"
        return self.out_dir / filename
    
    def list_all_files(self) -> list[Path]:
        """생성될 모든 파일 경로."""
        result = []
        for text_id, variants in self.files.items():
            for variant in variants.keys():
                result.append(self.get_output_path(text_id, variant))
        return result


def main():
    parser = argparse.ArgumentParser(
        description="WaggleBot LoRA 평가 — 텍스트 2개 × 3 설정 합성 + 측정",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""
        Example:
          python3 _evaluate_lora.py --checkpoint-label v1.0 --out-dir ./eval_results
          python3 _evaluate_lora.py --checkpoint-label v1.0 --out-dir ./eval_results --dry-run
        """),
    )
    
    parser.add_argument(
        "--checkpoint-label",
        required=True,
        help="LoRA 체크포인트 라벨 (예: v1.0, exp2)"
    )
    parser.add_argument(
        "--out-dir",
        required=True,
        help="출력 디렉토리"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="실제 작업 없이 계획만 출력"
    )
    
    args = parser.parse_args()
    
    out_dir = Path(args.out_dir)
    plan = EvaluationPlan(out_dir, args.checkpoint_label)
    
    # Dry-run 모드
    if args.dry_run:
        print("=" * 60)
        print("DRY RUN: 평가 계획")
        print("=" * 60)
        print(f"Checkpoint label: {args.checkpoint_label}")
        print(f"Output directory: {out_dir}")
        print(f"Synthesis tasks: {plan.count_synthesis_tasks()}")
        print()
        print("Files to be created:")
        for path in plan.list_all_files():
            print(f"  {path.name}")
        print()
        print("Texts:")
        print(f"  (a) kanola (DEFAULT_TEXT): {len(DEFAULT_TEXT)} chars")
        print(f"  (b) newstory (hardcoded): {len(NEW_STORY_TEXT)} chars")
        print()
        print("Note: corpus_chunks.json not found")
        print("  → using hardcoded new story text")
        print()
        print("Synthesis settings for all tasks:")
        print("  voice=typecast_ref")
        print("  speed=1.0")
        print("  loudnorm=relaxed")
        print("  pause=300ms")
        print()
        print("Variants:")
        print("  - 현행85% (synthesis with current settings)")
        print("  - LoRA (synthesis assuming fish-speech LoRA checkpoint)")
        print("  - 원본 (copy typecast_kanola.wav for kanola only)")
        print("=" * 60)
        return
    
    # 실제 실행 시 heavy imports 수행
    import asyncio
    import json
    import logging
    import shutil
    import subprocess
    
    from _ablation_tts import run_synthesis
    
    logging.basicConfig(
        level=logging.INFO,
        format="[%(levelname)s] %(message)s",
    )
    
    logger = logging.getLogger(__name__)
    
    # 실제 실행
    logger.info("평가 시작: checkpoint_label=%s", args.checkpoint_label)
    
    def get_reference_wav() -> Path:
        """원본 카놀라유 WAV 경로 반환."""
        repo_dir = Path(__file__).parent.parent
        ref_path = repo_dir / "assets" / "voices_raw" / "typecast_kanola.wav"
        if not ref_path.exists():
            raise FileNotFoundError(f"원본 WAV 미발견: {ref_path}")
        return ref_path
    
    def measure_audio(wav_path: Path, reference_path: Path | None = None) -> dict:
        """_measure_tts.py 호출로 오디오 측정."""
        cmd = ["python3", str(Path(__file__).parent / "_measure_tts.py"), str(wav_path)]
        
        if reference_path:
            cmd.extend(["--reference", str(reference_path)])
        
        logger.debug("측정 실행: %s", " ".join(cmd))
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
                cwd=str(Path(__file__).parent),
            )
            
            if result.returncode == 0:
                return json.loads(result.stdout)
            else:
                logger.warning("측정 실패 (rc=%d): %s", result.returncode, result.stderr[:200])
                return {"error": f"measurement failed: {result.stderr[:100]}"}
        
        except subprocess.TimeoutExpired:
            return {"error": "measurement timeout"}
        except Exception as e:
            return {"error": str(e)}
    
    async def synthesize_variant(text_id: str, variant: str, config: dict) -> Path:
        """한 가지 변형(variant) 합성."""
        output_path = plan.get_output_path(text_id, variant)
        
        if config.get("type") == "copy_reference":
            # 원본 복사
            source = get_reference_wav()
            logger.info("원본 복사: %s → %s", source.name, output_path.name)
            shutil.copy2(source, output_path)
            return output_path
        
        # 합성
        voice = config["voice"]
        text = config["text"]
        settings = config["settings"]
        
        logger.info("합성 시작: %s / %s (voice=%s)", text_id, variant, voice)
        
        await run_synthesis(
            voice=voice,
            text=text,
            speed=settings["speed"],
            loudnorm_policy=settings["loudnorm"],
            sentence_pause_ms=settings["pause_ms"],
            pronun_dict_enabled=False,  # 기본값
            output_path=output_path,
        )
        
        return output_path
    
    async def run_evaluation():
        """평가 실행."""
        results = {}
        ref_wav = get_reference_wav()
        
        for text_id in ["kanola", "newstory"]:
            results[text_id] = {}
            variants = plan.files[text_id]
            
            for variant, config in variants.items():
                try:
                    output_path = await synthesize_variant(text_id, variant, config)
                    
                    # 측정
                    ref_for_diff = None
                    if text_id == "kanola" and variant != "원본":
                        # 카놀라유는 원본과 비교
                        ref_for_diff = ref_wav
                    
                    metrics = measure_audio(output_path, ref_for_diff)
                    
                    results[text_id][variant] = {
                        "file": output_path.name,
                        "size_bytes": output_path.stat().st_size,
                        "metrics": metrics,
                    }
                    
                    logger.info("완료: %s / %s", text_id, variant)
                
                except Exception as e:
                    logger.error("실패: %s / %s — %s", text_id, variant, e, exc_info=True)
                    results[text_id][variant] = {
                        "error": str(e),
                    }
        
        # summary.json 저장
        summary_json = {
            "checkpoint_label": args.checkpoint_label,
            "results": results,
        }
        
        json_path = out_dir / "summary.json"
        json_path.write_text(json.dumps(summary_json, ensure_ascii=False, indent=2))
        logger.info("summary.json 저장: %s", json_path)
        
        # summary.md 생성
        md_content = generate_summary_md(args.checkpoint_label, results)
        md_path = out_dir / "summary.md"
        md_path.write_text(md_content, encoding="utf-8")
        logger.info("summary.md 저장: %s", md_path)
        
        logger.info("평가 완료")
    
    try:
        asyncio.run(run_evaluation())
    except Exception as exc:
        logger.error("평가 실패: %s", exc, exc_info=True)
        sys.exit(1)


def generate_summary_md(checkpoint_label: str, results: dict) -> str:
    """summary.md 생성."""
    lines = [
        f"# LoRA 평가 결과 — {checkpoint_label}",
        "",
        "## 개요",
        f"- **Checkpoint**: {checkpoint_label}",
        f"- **텍스트 2개** (카놀라유 사연 + 새 사연)",
        f"- **3가지 설정**: 현행85% / LoRA / 원본",
        "",
        "## 생성 파일",
        "",
    ]
    
    for text_id, variants in results.items():
        lines.append(f"### {text_id}")
        lines.append("")
        
        for variant, data in variants.items():
            if "error" in data:
                lines.append(f"- **{variant}**: ERROR — {data['error']}")
            else:
                file_name = data["file"]
                size_kb = data["size_bytes"] / 1024
                lines.append(f"- **{variant}**: {file_name} ({size_kb:.1f} KB)")
        
        lines.append("")
    
    lines.extend([
        "## 측정 결과",
        "",
        "### 카놀라유 사연",
        "",
        "| 설정 | 음성길이(초) | 침묵비율(%) | 다이나믹스(dB) |",
        "|---|---|---|---|",
    ])
    
    for variant, data in results.get("kanola", {}).items():
        if "error" not in data:
            metrics = data.get("metrics", {})
            duration = metrics.get("duration_sec", "—")
            silence_ratio = metrics.get("silence", {}).get("silence_ratio_pct", "—")
            loudness_range = metrics.get("dynamics", {}).get("loudness_range_db", "—")
            
            lines.append(f"| {variant} | {duration} | {silence_ratio} | {loudness_range} |")
    
    lines.extend([
        "",
        "### 새 사연",
        "",
        "| 설정 | 음성길이(초) | 침묵비율(%) | 다이나믹스(dB) |",
        "|---|---|---|---|",
    ])
    
    for variant, data in results.get("newstory", {}).items():
        if "error" not in data:
            metrics = data.get("metrics", {})
            duration = metrics.get("duration_sec", "—")
            silence_ratio = metrics.get("silence", {}).get("silence_ratio_pct", "—")
            loudness_range = metrics.get("dynamics", {}).get("loudness_range_db", "—")
            
            lines.append(f"| {variant} | {duration} | {silence_ratio} | {loudness_range} |")
    
    lines.extend([
        "",
        "## 참고",
        f"- 원본: `assets/voices_raw/typecast_kanola.wav`",
        f"- 새 사연: 코퍼스 없음 → 하드코딩 텍스트 사용",
        f"- LoRA 설정: fish-speech가 체크포인트로 전환된 상태 가정",
    ])
    
    return "\n".join(lines)


if __name__ == "__main__":
    main()
