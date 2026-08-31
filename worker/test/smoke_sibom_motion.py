"""시봄이 모션 렌더 스모크 (Phase 2 G2) — pytest 불필요, ffmpeg 불필요.

컨테이너 내부에서:
    python3 /app/test/smoke_sibom_motion.py
실제 프레임 렌더러로 punch/loop 프레임을 굽고, 프레임끼리 실제로 다른지
(=모션이 눈에 보이는지) 픽셀로 검증한 뒤 대비 시트를 남긴다.
"""
import copy
import sys
from pathlib import Path

sys.path.insert(0, "/app")

from ai_worker.renderer.layout import (  # noqa: E402
    _load_layout, _deep_merge, _wire_sibom_motion, _build_visual_timeline,
    _get_sibom_motion_for_image_id,
)
from ai_worker.renderer._frames import (  # noqa: E402
    _create_base_frame, _title_block_bottom_y, _render_image_text_frame,
)
from ai_worker.renderer.sibom_composite import composite_caption  # noqa: E402
from PIL import Image, ImageChops  # noqa: E402

FONT_DIR = Path("/app/assets/fonts")
OUT = Path("/app/media/tmp/smoke_sibom_motion")
OUT.mkdir(parents=True, exist_ok=True)
for f in OUT.glob("*.png"):
    f.unlink()

layout = copy.deepcopy(_load_layout())
tone_l = layout.get("themes", {}).get("tone_l", {})
_deep_merge(layout.setdefault("global", {}), tone_l.get("global", {}))
_deep_merge(layout.setdefault("scenes", {}), tone_l.get("scenes", {}))
layout["global"]["theme"] = "tone_l"
layout["global"]["header"]["channel_name"] = "다시봄"

title = "3년 사귄 남친이 상견례 자리에서 이럴 줄은 몰랐다"
meta = {"author": "다시봄", "time": "3시간 전", "views": "1.2만", "comments": 128}
content_top = _title_block_bottom_y(layout, title, FONT_DIR)
base = _create_base_frame(layout, title, FONT_DIR, Path("/app/assets"), meta=meta)

CASES = [("two-argue", "그 자리서 터졌다"), ("waiting-reply", "읽씹 사흘째"),
         ("drained", "이제 지쳤다"), ("burst-crying", "결국 울었다")]

fail = []
for case_i, (image_id, caption) in enumerate(CASES):
    motion = _get_sibom_motion_for_image_id(image_id)
    sibom = composite_caption(image_id, caption)
    text = "그 말을 듣고 나는 아무 말도 하지 못했다"

    def render_frame(img, out_path, _t=text):
        _render_image_text_frame(base, img, _t, layout, FONT_DIR, out_path,
                                 content_top, stage=2)

    entry = {"type": "image_text", "sibom_role": "peak",
             "sibom_image_id": image_id, "sibom_dwell": "hold"}
    _wire_sibom_motion(entry, render_frame, sibom, OUT, case_i)

    punch = [Path(p) for p in entry.get("sibom_punch_paths", [])]
    loop = [Path(p) for p in entry.get("sibom_loop_paths", [])]
    if not punch or not loop:
        fail.append(f"{image_id}: 프레임 미생성 (punch={len(punch)} loop={len(loop)})")
        continue

    def diff(a, b):
        return sum(ImageChops.difference(Image.open(a).convert("RGB"),
                                         Image.open(b).convert("RGB"))
                   .convert("L").getextrema())

    d_punch = diff(punch[0], punch[-1])
    # 사인 모션은 i=n/2에서 다시 0으로 돌아온다 — 최대 편차 지점을 찾아야 한다.
    loop_diffs = [(diff(loop[0], loop[i]), i) for i in range(1, len(loop))]
    d_loop, peak_i = max(loop_diffs)
    # 루프 이음매: 마지막 프레임과 첫 프레임이 크게 튀면 재생 시 끊겨 보인다
    d_seam = diff(loop[-1], loop[0])
    ok = d_punch > 0 and d_loop > 0 and d_seam <= d_loop
    print(f"{'OK ' if ok else 'FAIL'} {image_id:<14} motion={motion:<6} "
          f"punch={len(punch)} loop={len(loop)} "
          f"Δpunch={d_punch} Δloop={d_loop}@{peak_i} 이음매={d_seam}")
    if not ok:
        fail.append(f"{image_id}: Δpunch={d_punch} Δloop={d_loop} 이음매={d_seam} "
                    f"(0이면 모션 없음 / 이음매>Δloop면 루프가 튐)")

    tl = _build_visual_timeline([OUT / f"frame_{case_i:03d}.png"], [entry], [6.0])
    total = sum(d for _, d in tl)
    if abs(total - 6.0) > 0.01:
        fail.append(f"{image_id}: 타임라인 길이 {total:.3f} != 6.0")

    # 대비 시트 (등장 첫/끝 + 루프 0/중간)
    picks = [punch[0], punch[-1], loop[0], loop[peak_i]]
    ims = [Image.open(p).convert("RGB") for p in picks]
    w, h = ims[0].size
    sheet = Image.new("RGB", (w * len(ims), h), "white")
    for i, im in enumerate(ims):
        sheet.paste(im, (i * w, 0))
    sheet.thumbnail((1600, 1600))
    sheet.save(str(OUT / f"sheet_{image_id}.png"))

print("---")
if fail:
    print("실패:"); [print("  -", f) for f in fail]; sys.exit(1)
print(f"모두 통과 — 시트: {OUT}/sheet_*.png")
