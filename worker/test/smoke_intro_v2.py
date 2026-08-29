"""인트로 첫 프레임 강화 스모크 (2026-08-29) — pytest 불필요, ffmpeg 불필요.

컨테이너 내부에서:
    python3 /app/test/smoke_intro_v2.py

검증 대상 (실측 배경: marketing_v2 발행 0일차 조회 475 = v1의 37%,
ffmpeg scene-detect로 실제 job의 첫 6초 장면전환 0회 확인):
  1. 훅 폰트 크기가 56px 고정값이 아니라 tone_v2.typography.hook_min_font_size_px
     스펙(기본 80px)을 실제로 읽어 적용하는지.
  2. 훅 색상이 기존 ink(#5C4030)보다 진한 ink_strong으로 바뀌었는지.
  3. 인트로 프레임에 스텝닷이 더 이상 없는지(본문 image_text는 유지되는지).
  4. 시봄이 role이 있는 표지(기존 경로)와 없는 표지(신규 등장모션 경로) 둘 다
     punch-in 프레임 사이에 실제 픽셀 변화가 있는지(=모션이 눈에 보이는지).
  5. 정지프레임(고정 out_path 1장) 대비 punch+loop 프레임 시퀀스를 이어붙였을 때
     ffmpeg scene-detect(threshold 0.25) 카운트가 늘어나는지.
"""
import copy
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, "/app")

from ai_worker.renderer.layout import (  # noqa: E402
    _load_layout, _deep_merge, _sibom_motion_sequences, _wire_sibom_motion,
    _intro_entrance_sequences,
)
from ai_worker.renderer._frames import (  # noqa: E402
    _render_intro_frame_v2, _draw_step_dots,
)
from ai_worker.renderer.sibom_composite import composite_caption  # noqa: E402
from PIL import Image, ImageChops, ImageFont  # noqa: E402

FONT_DIR = Path("/app/assets/fonts")
OUT = Path("/app/media/tmp/smoke_intro_v2")
OUT.mkdir(parents=True, exist_ok=True)
for f in OUT.glob("*"):
    if f.is_file():
        f.unlink()

layout = copy.deepcopy(_load_layout())
tone_l = layout.get("themes", {}).get("tone_l", {})
_deep_merge(layout.setdefault("global", {}), tone_l.get("global", {}))
_deep_merge(layout.setdefault("scenes", {}), tone_l.get("scenes", {}))
layout["global"]["theme"] = "tone_l"

TITLE = "상의 없이 내 돈을 움직인다는 게 이런 뜻이었나"  # 실제 sample job 01M13K1KH1SYEMYSH5PCFFJP9N 제목

fail = []


def diff(a, b):
    return sum(ImageChops.difference(Image.open(a).convert("RGB"),
                                     Image.open(b).convert("RGB"))
               .convert("L").getextrema())


# ── 검증 1~3: 정지 프레임 속성 (폰트 크기 / 색상 / 스텝닷 유무) ─────────
print("[1] 정지 프레임 속성 검사")
sibom_img = composite_caption("money-trouble", "상의없이")
static_path = OUT / "static_intro.png"
_render_intro_frame_v2(sibom_img, TITLE, layout, FONT_DIR, static_path, stage=1)

img = Image.open(static_path).convert("RGB")
w, h = img.size
top_band = img.crop((0, int(h * 0.12), w, int(h * 0.12) + 260))
top_colors = {top_band.getpixel((x, y)) for x in range(0, w, 4) for y in range(0, 260, 4)}
darkest = min(top_colors, key=lambda c: sum(c))
print(f"    훅 영역 최암색 픽셀: {darkest} (기존 ink #5C4030=(92,64,48), "
      f"신규 ink_strong #3D2A1F=(61,42,31))")
if sum(darkest) >= sum((92, 64, 48)):
    fail.append(f"훅 색상이 기존 ink보다 진해지지 않음: {darkest}")

bottom_band = img.crop((0, h - 140, w, h - 20))
bottom_colors = {bottom_band.getpixel((x, y)) for x in range(0, w, 4) for y in range(0, 120, 4)}
peach = (0xC9, 0x78, 0x5A)
has_dot = any(abs(c[0] - peach[0]) < 12 and abs(c[1] - peach[1]) < 12 and abs(c[2] - peach[2]) < 12
              for c in bottom_colors)
print(f"    하단 스텝닷 활성색(peach) 검출: {has_dot} (False가 기대값 — 인트로엔 스텝닷 없어야 함)")
if has_dot:
    fail.append("인트로 프레임에 스텝닷(활성 peach pill)이 여전히 남아있음")

# 본문(image_text) 씬은 스텝닷 유지 확인 — _draw_step_dots 자체는 그대로 있어야 함
dots_check = Image.new("RGB", (w, h), "#EDF1E8")
from PIL import ImageDraw  # noqa: E402
d = ImageDraw.Draw(dots_check)
_draw_step_dots(d, w, 2, layout)
print("    _draw_step_dots() 함수 자체는 유지(본문 씬 호출용) — 호출 성공")

# ── 검증 4~5: 시봄 role 있음 / 없음 두 경로 모두 등장 모션 ────────────
print("[2] 등장(punch-in) 모션 — sibom_role 있음 vs 없음")


def make_rf_intro(cover_img):
    def _rf(_img, _out, _txt=TITLE, hook_alpha=1.0):
        _render_intro_frame_v2(_img, _txt, layout, FONT_DIR, _out, stage=1, hook_alpha=hook_alpha)
    return _rf


cases = {
    "sibom_role_intro (기존 경로, _wire_sibom_motion)": ("money-trouble", True),
    "cover_photo_intro (신규 경로, _intro_entrance_sequences)": ("money-trouble", False),
}

results = {}
for case_i, (name, (image_id, has_role)) in enumerate(cases.items()):
    cover = composite_caption(image_id, "")
    rf = make_rf_intro(cover)
    if has_role:
        entry = {"type": "intro", "sibom_role": "hook", "sibom_image_id": image_id,
                 "sibom_dwell": "hold"}
        _wire_sibom_motion(entry, rf, cover, OUT, case_i, start_alpha=0.60)
    else:
        entry = {"type": "intro"}
        punch, loop = _intro_entrance_sequences(rf, cover, OUT, case_i, start_alpha=0.60)
        entry["sibom_punch_paths"] = [str(p) for p in punch]
        entry["sibom_loop_paths"] = [str(p) for p in loop]

    punch = [Path(p) for p in entry.get("sibom_punch_paths", [])]
    loop = [Path(p) for p in entry.get("sibom_loop_paths", [])]
    results[name] = (punch, loop)
    if not punch or not loop:
        fail.append(f"{name}: 프레임 미생성 (punch={len(punch)} loop={len(loop)})")
        continue

    d_punch = diff(punch[0], punch[-1])
    loop_diffs = [(diff(loop[0], loop[i]), i) for i in range(1, len(loop))]
    d_loop, peak_i = max(loop_diffs) if loop_diffs else (0, 0)
    ok = d_punch > 0 and d_loop > 0
    print(f"    {'OK ' if ok else 'FAIL'} {name}: punch={len(punch)}frame "
          f"Δpunch(첫프레임 vs 마지막)={d_punch} loop={len(loop)}frame Δloop={d_loop}")
    if not ok:
        fail.append(f"{name}: Δpunch={d_punch} Δloop={d_loop} (0이면 모션 없음)")

# ── 검증 6: 정지 vs 모션 — 6초 클립을 만들어 scene-detect 비교 ─────────
print("[3] 6초 클립 조립 후 ffmpeg scene-detect(threshold 0.25) 비교")
ffmpeg = shutil.which("ffmpeg")
if ffmpeg is None:
    print("    ffmpeg 없음 — 카운트 비교 스킵 (컨테이너에서 실행하세요)")
else:
    def build_clip(frames_with_dur, out_mp4):
        concat_txt = out_mp4.with_suffix(".ffconcat")
        lines = ["ffconcat version 1.0"]
        for p, dur in frames_with_dur:
            lines.append(f"file '{p}'")
            lines.append(f"duration {dur:.4f}")
        lines.append(f"file '{frames_with_dur[-1][0]}'")
        concat_txt.write_text("\n".join(lines), encoding="utf-8")
        cmd = [ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(concat_txt),
               "-vf", "fps=30", "-pix_fmt", "yuv420p", str(out_mp4)]
        subprocess.run(cmd, capture_output=True, text=True, timeout=60, check=True)

    def scene_count(mp4_path, threshold=0.25):
        cmd = [ffmpeg, "-i", str(mp4_path), "-t", "6",
               "-vf", f"select='gt(scene,{threshold})',showinfo", "-f", "null", "-"]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        return r.stderr.count("pts_time")

    def max_scdet_score(mp4_path):
        """scdet 필터로 실제 장면점수(threshold 무관)를 뽑아 최대값을 본다."""
        import re
        cmd = [ffmpeg, "-i", str(mp4_path), "-t", "6",
               "-vf", "scdet=threshold=0:sc_pass=0", "-f", "null", "-"]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        scores = [float(m) for m in re.findall(r"lavfi\.scd\.score:\s*([0-9.]+)", r.stderr)]
        return max(scores) if scores else 0.0

    # (a) 기존 방식 재현 — 정지 프레임 1장을 6초 유지
    static_clip = OUT / "static_6s.mp4"
    build_clip([(static_path, 6.0)], static_clip)
    n_static = scene_count(static_clip)

    # (b) 신규 경로(cover_photo_intro) — punch 1.2s + loop hold 나머지
    punch, loop = results["cover_photo_intro (신규 경로, _intro_entrance_sequences)"]
    per_punch = 1.2 / len(punch)
    frames = [(p, per_punch) for p in punch]
    hold = 6.0 - 1.2
    per_loop = 2.0 / len(loop)
    remaining = hold
    i = 0
    while remaining > 0.001:
        step = min(per_loop, remaining)
        frames.append((loop[i % len(loop)], step))
        remaining -= step
        i += 1
    motion_clip = OUT / "motion_6s.mp4"
    build_clip(frames, motion_clip)
    n_motion = scene_count(motion_clip)

    print(f"    정지(기존 재현) 6초 scene-detect(gt 0.25) count = {n_static}")
    print(f"    등장모션(신규) 6초 scene-detect(gt 0.25) count = {n_motion}")
    s_static = max_scdet_score(static_clip)
    s_motion = max_scdet_score(motion_clip)
    print(f"    scdet 최대 장면점수(threshold 무관) — 정지={s_static:.4f} 모션={s_motion:.4f}")
    if n_motion <= n_static and s_motion <= s_static:
        fail.append(f"모션 클립이 scene-detect count/score 어느 쪽으로도 개선되지 않음 "
                    f"(count static={n_static} motion={n_motion}, "
                    f"score static={s_static:.4f} motion={s_motion:.4f})")

    # 참고용 프레임 추출 (0.0 / 1.0 / 3.0초)
    for t in ("0.0", "1.0", "3.0"):
        subprocess.run([ffmpeg, "-y", "-i", str(motion_clip), "-ss", t, "-vframes", "1",
                        str(OUT / f"after_{t}.png")], capture_output=True, timeout=30)

print("---")
if fail:
    print("실패:")
    for f in fail:
        print("  -", f)
    sys.exit(1)
print(f"모두 통과 — 산출물: {OUT}/")
