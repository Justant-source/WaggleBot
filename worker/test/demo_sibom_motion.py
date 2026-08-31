#!/usr/bin/env python3
"""시봄이 모션 쇼케이스 — 사연 파이프라인(LLM·TTS) 없이 애니메이션만 보여준다.

🚨 모션 수식을 여기서 새로 만들지 말 것.
   반드시 `ai_worker.renderer.layout`의 **실제 프로덕션 함수**를 호출한다.
   (초판이 자체 sway/shake를 따로 구현해 실제 영상과 다른 걸 보여준 적이 있다.)

컨테이너 실행:
    docker exec env-ai_worker-1 python3 /app/test/demo_sibom_motion.py
출력:
    /app/media/video/demo/sibom_motion_demo.mp4
    → http://<host>:8080/api/media/video/demo/sibom_motion_demo.mp4
"""
import logging
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, "/app")

from PIL import Image, ImageDraw, ImageFont  # noqa: E402

from ai_worker.renderer.layout import (  # noqa: E402
    _sibom_motion_sequences,
    _sibom_variant,
    _SIBOM_BREATHE_CYCLE_SEC,
    _SIBOM_PUNCH_SEC,
)

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("demo_sibom")

CANVAS_W, CANVAS_H = 1080, 1920
FPS = 30
CREAM_BG = "#FBF3EC"
INK = "#5C4030"
MUTED = "#8A7A6A"

CHAR_BASE_W = 980          # 캐릭터 기준 폭 (모션 scale이 여기에 곱해진다)
CHAR_TOP_Y = 470
LOOP_CYCLES = 3

SPROUTS = Path("/app/assets/sprouts/png")
OUT_DIR = Path("/app/media/video/demo")
TMP = OUT_DIR / "tmp"

# 실제 catalog의 motion 값과 같은 것을 쓴다.
SECTIONS = [
    ("sway", "waiting-reply", "기본 — 숨쉬기", "sway · 모든 씬의 기본 idle"),
    ("shake", "two-argue", "분노 — 잔떨림", "shake · two-argue · indignant · stunned"),
    ("sob", "burst-crying", "울음 — 들썩임", "sob · burst-crying"),
    ("sink", "drained", "지침 — 처짐", "sink · drained · overloaded · curled-up"),
    ("pop", "reconciled", "안도 — 크게 숨쉬기", "pop · reconciled · relieved"),
]


def font(size: int):
    for p in ("/app/assets/fonts/NotoSansKR-Bold.ttf",
              "/app/assets/fonts/NotoSansKR-Regular.ttf",
              "/usr/share/fonts/truetype/noto/NotoSansKR-Bold.ttf"):
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _center(draw, text, y, f, fill):
    b = draw.textbbox((0, 0), text, font=f)
    draw.text(((CANVAS_W - (b[2] - b[0])) // 2, y), text, fill=fill, font=f)


def compose(char_img, title, label, sub):
    """변형된 캐릭터를 데모 캔버스에 올린다."""
    frame = Image.new("RGB", (CANVAS_W, CANVAS_H), CREAM_BG)
    d = ImageDraw.Draw(frame)
    _center(d, title, 90, font(72), INK)

    k = CHAR_BASE_W / max(1, char_img.width)
    w, h = int(char_img.width * k), int(char_img.height * k)
    ov = char_img.convert("RGBA").resize((w, h), Image.Resampling.LANCZOS)
    frame.paste(ov, ((CANVAS_W - w) // 2, CHAR_TOP_Y), ov)

    _center(d, label, CANVAS_H - 300, font(64), INK)
    _center(d, sub, CANVAS_H - 210, font(38), MUTED)
    return frame


def build_section(motion, image_id, label, sub, idx):
    """실제 프로덕션 모션 시퀀스로 한 구간을 만든다."""
    src = SPROUTS / f"{image_id}.png"
    if not src.exists():
        logger.warning("이미지 없음: %s", src)
        return []
    sibom = Image.open(src).convert("RGBA")

    def render_frame(img, out_path):
        compose(img, "시봄이 모션", label, sub).save(str(out_path), "PNG")

    punch, loop = _sibom_motion_sequences(
        render_frame, sibom, motion, TMP, idx,
    )
    seq = [(p, _SIBOM_PUNCH_SEC / max(1, len(punch))) for p in punch]
    if loop:
        per = _SIBOM_BREATHE_CYCLE_SEC / len(loop)
        for _ in range(LOOP_CYCLES):
            seq += [(p, per) for p in loop]
    logger.info("  %-6s %-14s punch=%d loop=%d", motion, image_id, len(punch), len(loop))
    return seq


def build_comparison(idx):
    """모션 없음(기존) vs 있음 — 차이를 직접 보여주는 구간."""
    sibom = Image.open(SPROUTS / "waiting-reply.png").convert("RGBA")
    seq = []

    still = TMP / f"cmp_{idx:03d}_still.png"
    compose(sibom, "모션 없음 (기존)", "정지 이미지", "등장 후 그대로 멈춰 있었다").save(str(still), "PNG")
    seq.append((still, 2.5))

    def render_frame(img, out_path):
        compose(img, "모션 있음 (신규)", "숨쉬기 + 등장 팝인", "sway").save(str(out_path), "PNG")

    punch, loop = _sibom_motion_sequences(render_frame, sibom, "sway", TMP, idx + 100)
    seq += [(p, _SIBOM_PUNCH_SEC / max(1, len(punch))) for p in punch]
    if loop:
        per = _SIBOM_BREATHE_CYCLE_SEC / len(loop)
        for _ in range(2):
            seq += [(p, per) for p in loop]
    return seq


def encode(seq, out_mp4):
    lst = TMP / "concat.txt"
    with lst.open("w") as f:
        for p, dur in seq:
            f.write(f"file '{p}'\nduration {dur:.6f}\n")
        f.write(f"file '{seq[-1][0]}'\n")      # ffconcat 마지막 항목은 duration 없이 한 번 더
    subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0",
         "-i", str(lst), "-vsync", "cfr", "-r", str(FPS),
         "-pix_fmt", "yuv420p", "-c:v", "libx264", "-preset", "fast", "-crf", "23",
         str(out_mp4)],
        check=True,
    )


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    TMP.mkdir(parents=True, exist_ok=True)
    for f in TMP.glob("*.png"):
        f.unlink()

    seq = []
    for i, (motion, image_id, label, sub) in enumerate(SECTIONS):
        seq += build_section(motion, image_id, label, sub, i)
    seq += build_comparison(len(SECTIONS))

    if not seq:
        logger.error("프레임이 하나도 없다 — 중단")
        return 1

    out = OUT_DIR / "sibom_motion_demo.mp4"
    encode(seq, out)
    total = sum(d for _, d in seq)
    logger.info("완료: %s (%d프레임, %.1f초)", out, len(seq), total)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
