"""훅 구간(인트로 첫 3~4초) 디자인 실험 프로필 — 2026-10-18.

배경: YouTube Shorts 84건 분석 결과 정적 카드 + 시봄이 한 쌍 + 한 단어 라벨이라
조회 1,148짜리와 14짜리가 시각적으로 구분되지 않는다. 첫 3초가 정적이라 스크롤을
못 멈춘다는 가설을 검증하려고, 본문은 marketing_v2 와 완전히 동일하게 두고
**인트로 장면만** 바꾼 3개 변형을 둔다.

  marketing_hook_a  숫자·금액 강조(색+확대+하이라이트) + 훅 글자 확대(96px 목표)
  marketing_hook_b  단어 순차 팝인(키네틱 타이포, 0~T초) → 카드 등장 → 기존 인트로
  marketing_hook_c  첫 1.5초 시봄이 리액션 클로즈업 + 짧은 자막 → 하드 컷으로 훅 문장 카드

설계 원칙
- 프로필 이름은 layout._render_pipeline 진입 즉시 base_profile()로 marketing_v2 로 접는다.
  BGM·SFX·세그먼트 경로·댓글 배율 등 본문 분기는 전부 v2 와 같은 코드를 탄다.
- 인트로 정지 프레임(frame_paths[idx])은 기존 `_render_intro_frame_v2` 가 만든 것을
  그대로 폴백으로 둔다(A 는 확대·강조 버전으로 교체). 애니메이션은 별도 타임라인
  (PNG + 길이 목록)으로 구워 `render_timeline_segment` 가 mp4 한 조각으로 만든다.
- safe_zone(tone_v2.safe_zone: 상 12%·하 22%)은 건드리지 않고 그대로 존중한다.

한계
- TTS 오디오는 건드리지 않는다(낭독은 0초부터). C 는 훅 문장이 1.5~1.8초에 나타나므로
  그 사이 낭독이 자막보다 앞선다. B 는 단어가 낭독보다 빠르게(T=최대 3초) 먼저 뜬다.
- 숫자 강조는 아라비아 숫자로 시작하는 토큰만 잡는다("백팔십만원" 같은 한글 수사는 못 잡음).
"""
from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw

logger = logging.getLogger(__name__)

HOOK_PROFILES = ("marketing_hook_a", "marketing_hook_b", "marketing_hook_c")

_BG = "#EDF1E8"
_FPS = 15                      # 애니메이션 구간 프레임 레이트 (정지 구간은 길이로 흡수)
_NUM_COLOR = "#C8431F"         # 숫자 강조색 (진영색 피치/세이지와 겹치지 않는 붉은 주황)
_NUM_BAND = "#F7DCC0"          # 숫자 뒤 하이라이트 밴드
_NUM_SCALE = 1.3               # 숫자 확대 비율
_A_TARGET_FS = 96              # A 훅 목표 크기 (v2 현행 80px 대비 +20%)
_A_MIN_FS = 88                 # 4줄 이내면 이 아래로 줄이지 않는다(v2 80px 보다 큼)

# 아라비아 숫자로 시작하는 수량 표현. 단위는 긴 것부터 매칭한다.
_NUM_RE = re.compile(
    r"\d[\d,\.]*(?:만원|억원|천원|백원|퍼센트|개월|시간|주일|%|원|만|억|번|년|달|주|일|분|초|살|세|명|개|배|"
    r"kg|km|시|월|위|호|평|채|곳|장|통|잔|병|대|등|차례|가지|군데)?"
)


def is_hook_profile(profile: Optional[str]) -> bool:
    return profile in HOOK_PROFILES


def base_profile(profile: Optional[str]) -> Optional[str]:
    """훅 실험 프로필은 본문 분기에서 marketing_v2 로 취급한다."""
    return "marketing_v2" if is_hook_profile(profile) else profile


# ---------------------------------------------------------------------------
# 공통 도우미
# ---------------------------------------------------------------------------

def _ease_out(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 1.0 - (1.0 - t) ** 3


def _ease_in_out(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def _geom(layout: dict):
    cw = layout["canvas"]["width"]
    ch = layout["canvas"]["height"]
    pad_x = layout["global"].get("title_block", {}).get("pad_x", 90)
    palette = layout["global"].get("palette", {})
    return cw, ch, pad_x, palette


def _hook_target_fs() -> int:
    from ai_worker.renderer.layout import _load_renderer_settings
    try:
        typo = (_load_renderer_settings().get("tone_v2") or {}).get("typography") or {}
        return int(typo.get("hook_min_font_size_px", 80))
    except Exception:
        return 80


def _new_canvas(layout: dict) -> Image.Image:
    cw, ch, _, _ = _geom(layout)
    return Image.new("RGB", (cw, ch), _BG)


def _draw_ribbon_on(img: Image.Image, layout: dict) -> None:
    from ai_worker.renderer._frames import _draw_ribbon
    cw, ch, _, _ = _geom(layout)
    _draw_ribbon(ImageDraw.Draw(img), cw, ch, layout)


def _tokens(text: str) -> list[str]:
    # 하드 개행은 공백으로 접는다(v2 인트로도 한 문장으로 래핑한다)
    return [t for t in (text or "").replace("\r", " ").replace("\n", " ").split(" ") if t]


def _wrap_tokens(tokens: list[str], font, max_w: int) -> list[list[str]]:
    """어절 단위 줄바꿈(keep_all). 한 어절이 한 줄보다 길면 그 어절만 단독 줄."""
    from ai_worker.renderer._frames import _font_w
    lines: list[list[str]] = []
    cur: list[str] = []
    for tok in tokens:
        cand = " ".join(cur + [tok])
        if not cur or _font_w(font, cand) <= max_w:
            cur.append(tok)
        else:
            lines.append(cur)
            cur = [tok]
    if cur:
        lines.append(cur)
    return lines or [[""]]


def _v2_hook_layout(title: str, layout: dict, font_dir: Path):
    """v2 인트로와 같은 규칙(목표 80px, 3줄 넘으면 64px까지 축소)으로 훅을 배치한다.

    v2 는 3줄을 넘는 문구를 잘라 버린다(`t_lines[:3]`). 실험군은 문구를 자르지 않는다 —
    64px 에서도 3줄을 넘으면 4줄까지 허용한다(카드가 그만큼 작아질 뿐).
    """
    from ai_worker.renderer.layout import _load_font
    from ai_worker.renderer._frames import _body_font_file
    cw, ch, pad_x, _ = _geom(layout)
    max_w = cw - 2 * pad_x
    fs = _hook_target_fs()
    font_file = _body_font_file(layout)
    font = _load_font(font_dir, font_file, fs)
    toks = _tokens(title)
    lines = _wrap_tokens(toks, font, max_w)
    while len(lines) > 3 and fs > 64:
        fs = max(64, fs - 4)
        font = _load_font(font_dir, font_file, fs)
        lines = _wrap_tokens(toks, font, max_w)
    return fs, font, lines


def _paste_alpha(img: Image.Image, layer: Image.Image, xy: tuple[int, int], alpha: float = 1.0) -> None:
    """RGBA layer 를 알파 배율을 적용해 img(RGB)에 합성."""
    if alpha <= 0.002:
        return
    if alpha < 0.999:
        layer = layer.copy()
        layer.putalpha(layer.getchannel("A").point(lambda v: int(v * alpha)))
    img.paste(layer, xy, layer)


def _card_layer(img_pil: Optional[Image.Image], card_y: int, layout: dict):
    """v2 인트로 카드(흰 둥근 사각 + contain 캐릭터)를 RGBA 레이어로. (layer, (x, y))."""
    from ai_worker.renderer._frames import _fit_contain
    cw, ch, pad_x, _ = _geom(layout)
    card_cfg = layout["scenes"]["image_text"].get("card", {})
    card_pad = card_cfg.get("pad", 44)
    card_radius = card_cfg.get("radius", 28)
    card_w = cw - 2 * pad_x
    inner = card_w - 2 * card_pad
    safe_bottom = int(ch * 0.22)
    inner = min(inner, max(120, ch - safe_bottom - card_y - 2 * card_pad))
    card_h = card_pad * 2 + inner
    layer = Image.new("RGBA", (card_w, card_h), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rounded_rectangle([(0, 0), (card_w - 1, card_h - 1)], radius=card_radius, fill="#FFFFFF")
    if img_pil is not None:
        fitted = _fit_contain(img_pil, inner, inner)
        ox = card_pad + (inner - fitted.width) // 2
        oy = card_pad + (inner - fitted.height) // 2
        layer.paste(fitted, (ox, oy), fitted if fitted.mode == "RGBA" else None)
    return layer, (pad_x, card_y)


# ---------------------------------------------------------------------------
# A — 숫자 강조 + 대형 훅
# ---------------------------------------------------------------------------

def _split_numbers(token: str) -> list[tuple[str, bool]]:
    """토큰을 (텍스트, 숫자여부) 조각으로 나눈다."""
    out: list[tuple[str, bool]] = []
    pos = 0
    for m in _NUM_RE.finditer(token):
        if m.start() > pos:
            out.append((token[pos:m.start()], False))
        out.append((m.group(0), True))
        pos = m.end()
    if pos < len(token):
        out.append((token[pos:], False))
    return out or [(token, False)]


def has_number(text: str) -> bool:
    return bool(_NUM_RE.search(text or ""))


def _layout_a(title: str, layout: dict, font_dir: Path):
    """A 의 줄/조각 배치. 반환: (fs, lines, line_heights) — lines[i] = [(text,is_num,x,w)]"""
    from ai_worker.renderer.layout import _load_font
    from ai_worker.renderer._frames import _body_font_file
    cw, ch, pad_x, _ = _geom(layout)
    max_w = cw - 2 * pad_x - 8      # 실측 폭(getlength) 기준 + 측정오차 여유
    font_file = _body_font_file(layout)
    toks = _tokens(title)

    def _font_w(font, txt: str) -> float:   # 슬랙 없는 실제 advance (조사가 숫자와 벌어지지 않게)
        return float(font.getlength(txt))

    def build(fs: int):
        f = _load_font(font_dir, font_file, fs)
        nf = _load_font(font_dir, font_file, int(fs * _NUM_SCALE))

        def tok_w(tok: str) -> float:
            w = 0.0
            for txt, is_num in _split_numbers(tok):
                w += _font_w(nf if is_num else f, txt)
            return w

        space_w = _font_w(f, " ")
        rows: list[list[str]] = []
        cur: list[str] = []
        cur_w = 0.0
        for tok in toks:
            tw = tok_w(tok)
            add = tw if not cur else space_w + tw
            if not cur or cur_w + add <= max_w:
                cur.append(tok)
                cur_w += add
            else:
                rows.append(cur)
                cur, cur_w = [tok], tw
        if cur:
            rows.append(cur)
        return f, nf, rows or [[""]], space_w

    fs = _A_TARGET_FS
    f, nf, rows, space_w = build(fs)
    # 현행 v2(80px)보다 항상 크게: 88px 이상을 유지하며 4줄까지 허용한다(카드가 그만큼 작아짐).
    # 4줄을 넘는 아주 긴 훅만 예외로 72px 까지 축소.
    while len(rows) > 4 and fs > _A_MIN_FS:
        fs -= 4
        f, nf, rows, space_w = build(fs)
    while len(rows) > 4 and fs > 72:
        fs -= 4
        f, nf, rows, space_w = build(fs)

    placed: list[list[tuple[str, bool, int, int]]] = []
    for row in rows:
        x = float(pad_x)
        pieces: list[tuple[str, bool, int, int]] = []
        for ti, tok in enumerate(row):
            if ti:
                x += space_w
            for txt, is_num in _split_numbers(tok):
                w = _font_w(nf if is_num else f, txt)
                pieces.append((txt, is_num, int(x), int(w)))
                x += w
        placed.append(pieces)
    return fs, f, nf, placed


def _render_a_frame(title: str, img_pil, layout: dict, font_dir: Path, out_path: Path,
                    num_scale: float = 1.0, num_alpha: float = 1.0) -> Path:
    cw, ch, pad_x, palette = _geom(layout)
    fs, f, nf, placed = _layout_a(title, layout, font_dir)
    img = _new_canvas(layout)
    draw = ImageDraw.Draw(img)
    safe_top = int(ch * 0.12)
    hook_color = palette.get("ink_strong", "#3D2A1F")
    lh = int(fs * _NUM_SCALE * 1.2) if any(p[1] for row in placed for p in row) else int(fs * 1.25)
    base_lh = int(fs * 1.25)
    y = safe_top
    for row in placed:
        row_has_num = any(p[1] for p in row)
        row_h = lh if row_has_num else base_lh
        baseline = y + int(row_h * 0.82)
        for txt, is_num, x, w in row:
            if not is_num:
                draw.text((x, baseline), txt, font=f, fill=hook_color, anchor="ls")
        # 숫자는 레이어로 그려 팝(확대/알파)을 줄 수 있게 한다
        for txt, is_num, x, w in row:
            if not is_num:
                continue
            nfs = int(fs * _NUM_SCALE)
            padb = 10
            lw, lhh = w + 2 * padb, int(nfs * 1.15)
            layer = Image.new("RGBA", (lw, lhh), (0, 0, 0, 0))
            ld = ImageDraw.Draw(layer)
            ld.rounded_rectangle([(0, int(nfs * 0.12)), (lw - 1, lhh - 1)], radius=14, fill=_NUM_BAND)
            ld.text((padb, int(nfs * 0.98)), txt, font=nf, fill=_NUM_COLOR, anchor="ls")
            if abs(num_scale - 1.0) > 0.001:
                nw, nh = max(1, int(lw * num_scale)), max(1, int(lhh * num_scale))
                layer = layer.resize((nw, nh), Image.LANCZOS)
            # 밴드 하단이 baseline 아래 약간 내려오도록 정렬: 레이어 중심을 기준으로 스케일
            cx = x - padb + lw // 2
            cy = baseline - int(nfs * 0.98) + lhh // 2
            _paste_alpha(img, layer, (cx - layer.width // 2, cy - layer.height // 2), num_alpha)
        y += row_h
    layer, (cx0, cy0) = _card_layer(img_pil, y + 48, layout)
    _paste_alpha(img, layer, (cx0, cy0))
    _draw_ribbon_on(img, layout)
    img.save(str(out_path), "PNG")
    return out_path


def _timeline_a(title, img_pil, layout, font_dir, tmp_dir: Path, tag: str, total: float):
    final = tmp_dir / f"{tag}_hookA_final.png"
    _render_a_frame(title, img_pil, layout, font_dir, final)
    if not has_number(title):
        logger.info("[hook_a] 훅에 숫자 없음 — 강조 없이 확대 훅만 적용: %r", title)
        return final, [(final, total)]
    scales = [0.85, 1.28, 1.16, 1.07, 1.02]
    tl: list[tuple[Path, float]] = []
    for i, s in enumerate(scales):
        p = tmp_dir / f"{tag}_hookA_{i:02d}.png"
        _render_a_frame(title, img_pil, layout, font_dir, p, num_scale=s, num_alpha=1.0)
        tl.append((p, 1.0 / _FPS))
    tl.append((final, max(0.0, total - len(scales) / _FPS)))
    return final, tl


# ---------------------------------------------------------------------------
# B — 키네틱 타이포
# ---------------------------------------------------------------------------

def _timeline_b(title, img_pil, layout, font_dir, tmp_dir: Path, tag: str, total: float):
    from ai_worker.renderer._frames import _render_intro_frame_v2
    cw, ch, pad_x, palette = _geom(layout)
    fs, font, lines = _v2_hook_layout(title, layout, font_dir)
    lh = int(fs * 1.25)
    safe_top = int(ch * 0.12)
    safe_bottom = int(ch * 0.22)
    hook_color = palette.get("ink_strong", "#3D2A1F")

    final = tmp_dir / f"{tag}_hookB_final.png"
    # 정지 최종 프레임 = 기존 v2 인트로 그대로 (훅 구간만 변수)
    _render_intro_frame_v2(img_pil, title, layout, font_dir, final)

    # 단어 목록과 최종 위치(y0 = safe_top 기준)
    words: list[tuple[str, int, int]] = []   # (text, x, line_idx)
    for li, row in enumerate(lines):
        for wi, w in enumerate(row):
            prefix = " ".join(row[:wi])
            x = pad_x + (int(font.getlength(prefix + " ")) if prefix else 0)
            words.append((w, x, li))
    n = len(words)
    if n == 0:
        return final, [(final, total)]

    block_h = len(lines) * lh
    region_h = ch - safe_top - safe_bottom
    y_center = safe_top + max(0, (region_h - block_h) // 2) - 60
    y_final = safe_top

    t_k = max(1.0, min(3.0, total * 0.7))        # 키네틱 길이 (최대 3초)
    t_move = 0.5                                  # 카드 등장 + 블록 이동
    step = min(0.5, t_k / n)                      # 단어 간격 (0.5초 상한)
    pop = 0.25
    t_end = t_k + t_move
    if t_end > total:                             # 인트로가 짧으면 압축
        t_k = max(0.8, total - t_move)
        step = min(0.5, t_k / n)
        t_end = min(total, t_k + t_move)
    starts = [i * step - 0.12 for i in range(n)]   # 첫 단어는 0초 프레임에 이미 보이게(썸네일 후보)

    tl: list[tuple[Path, float]] = []
    nframes = int(t_end * _FPS)
    for fi in range(nframes):
        t = fi / _FPS
        img = _new_canvas(layout)
        # 블록 y: 키네틱 동안 가운데, 이후 final 로 이동
        k = _ease_in_out((t - t_k) / t_move) if t > t_k else 0.0
        y0 = int(y_center + (y_final - y_center) * k)
        for wi, (txt, x, li) in enumerate(words):
            tr = (t - starts[wi]) / pop
            if tr < 0:
                continue
            p = _ease_out(tr)
            sc = 1.0 + 0.45 * (1.0 - p)
            wl = int(font.getlength(txt)) + 8
            wh = int(fs * 1.4)
            layer = Image.new("RGBA", (wl, wh), (0, 0, 0, 0))
            ImageDraw.Draw(layer).text((4, int(wh * 0.82)), txt, font=font, fill=hook_color, anchor="ls")
            if sc > 1.001:
                layer = layer.resize((int(wl * sc), int(wh * sc)), Image.LANCZOS)
            cx = x - 4 + wl // 2
            cy = y0 + li * lh + wh // 2 - int(fs * 0.1) + int((1.0 - p) * 18)
            _paste_alpha(img, layer, (cx - layer.width // 2, cy - layer.height // 2), p)
        if t > t_k:
            cl, (cx0, cy0) = _card_layer(img_pil, y0 + len(lines) * lh + 48, layout)   # 카드는 글 블록과 함께 올라와 겹치지 않는다
            _paste_alpha(img, cl, (cx0, cy0), _ease_out((t - t_k) / t_move))
        _draw_ribbon_on(img, layout)
        p_out = tmp_dir / f"{tag}_hookB_{fi:03d}.png"
        img.save(str(p_out), "PNG")
        tl.append((p_out, 1.0 / _FPS))
    tl.append((final, max(0.0, total - nframes / _FPS)))
    return final, tl


# ---------------------------------------------------------------------------
# C — 캐릭터 리액션 클로즈업 먼저
# ---------------------------------------------------------------------------

def _tight_crop(im: Image.Image, pad: int = 36) -> Image.Image:
    """스프라이트 정사각의 빈 여백을 잘라 캐릭터가 더 크게 보이게 한다(클로즈업)."""
    from PIL import ImageChops
    rgb = im.convert("RGB")
    bg = rgb.getpixel((2, 2))
    diff = ImageChops.difference(rgb, Image.new("RGB", rgb.size, bg)).convert("L")
    bbox = diff.point(lambda v: 255 if v > 28 else 0).getbbox()
    if not bbox:
        return im
    l, t, r, b = bbox
    l, t = max(0, l - pad), max(0, t - pad)
    r, b = min(im.width, r + pad), min(im.height, b + pad)
    return im.crop((l, t, r, b))


def _round_corners(im: Image.Image, radius: int) -> Image.Image:
    im = im.convert("RGBA")
    mask = Image.new("L", im.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([(0, 0), (im.width - 1, im.height - 1)], radius=radius, fill=255)
    out = Image.new("RGBA", im.size, (0, 0, 0, 0))
    out.paste(im, (0, 0), mask)
    return out


def _short_caption(title: str) -> str:
    toks = _tokens(title)
    out = ""
    for t in toks:
        cand = (out + " " + t).strip()
        if len(cand) > 12 and out:
            break
        out = cand
        if len(out) >= 8:
            break
    return (out[:12] + "…") if out else ""


def _timeline_c(title, img_pil, layout, font_dir, tmp_dir: Path, tag: str, total: float):
    from ai_worker.renderer._frames import _render_intro_frame_v2, _fit_contain, _body_font_file
    from ai_worker.renderer.layout import _load_font
    cw, ch, pad_x, palette = _geom(layout)
    final = tmp_dir / f"{tag}_hookC_final.png"
    _render_intro_frame_v2(img_pil, title, layout, font_dir, final)
    if img_pil is None:
        logger.warning("[hook_c] 캐릭터 이미지 없음 — 클로즈업 불가, v2 인트로로 대체")
        return final, [(final, total)]

    t_close = min(1.5, max(0.8, total * 0.45))
    safe_top = int(ch * 0.12)
    safe_bottom = int(ch * 0.22)
    hook_color = palette.get("ink_strong", "#3D2A1F")
    cap_fs = 64
    cap_font = _load_font(font_dir, _body_font_file(layout), cap_fs)
    caption = _short_caption(title)

    max_zoom = 1.07
    box_w = cw - 2 * 60
    box_h = int((ch - safe_top - safe_bottom) * 0.74)
    base = _fit_contain(_tight_crop(img_pil), int(box_w / max_zoom), int(box_h / max_zoom))
    base = _round_corners(base, 36)
    area_cy = safe_top + int((ch - safe_top - safe_bottom) * 0.42)

    def close_frame(t: float) -> Image.Image:
        img = _new_canvas(layout)
        zoom = 1.0 + (max_zoom - 1.0) * min(1.0, t / t_close)
        w, h = max(1, int(base.width * zoom)), max(1, int(base.height * zoom))
        z = base.convert("RGBA").resize((w, h), Image.LANCZOS)
        img.paste(z, ((cw - w) // 2, area_cy - h // 2), z)
        d = ImageDraw.Draw(img)
        if caption:
            cy = min(area_cy + h // 2 + 40, ch - safe_bottom - cap_fs - 20)
            cl = int(cap_font.getlength(caption))
            d.text(((cw - cl) // 2, cy), caption, font=cap_font, fill=hook_color)
        _draw_ribbon_on(img, layout)
        return img

    tl: list[tuple[Path, float]] = []
    n_close = max(1, int(t_close * _FPS))
    last_close = None
    for fi in range(n_close):
        last_close = close_frame(fi / _FPS)
        p = tmp_dir / f"{tag}_hookC_{fi:03d}.png"
        last_close.save(str(p), "PNG")
        tl.append((p, 1.0 / _FPS))
    # 클로즈업 → 훅 카드는 하드 컷. 배치가 전혀 다른 두 장을 크로스페이드하면 겹침이 지저분하다
    # (실측 프레임 확인). 컷 자체가 장면 전환으로 잡혀 이탈 방지 효과도 있다.
    used = n_close / _FPS
    tl.append((final, max(0.0, total - used)))
    return final, tl


# ---------------------------------------------------------------------------
# 공개 API
# ---------------------------------------------------------------------------

def build_hook_timeline(variant: str, img_pil, title: str, layout: dict, font_dir: Path,
                        tmp_dir: Path, frame_idx: int, total: float):
    """(정지 최종 프레임 경로, [(png, 길이초), ...]) — 합계 길이 == total.

    final 은 인트로 정지 프레임(frame_paths[idx])을 대체하는 용도(폴백·썸네일)다.
    A 는 확대·강조 버전, B/C 는 v2 기본 인트로 그대로다.
    """
    tag = f"intro_{frame_idx:03d}"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    if variant == "marketing_hook_a":
        return _timeline_a(title, img_pil, layout, font_dir, tmp_dir, tag, total)
    if variant == "marketing_hook_b":
        return _timeline_b(title, img_pil, layout, font_dir, tmp_dir, tag, total)
    if variant == "marketing_hook_c":
        return _timeline_c(title, img_pil, layout, font_dir, tmp_dir, tag, total)
    raise ValueError(f"unknown hook variant: {variant}")


def render_timeline_segment(timeline: list[tuple[Path, float]], total: float, out_path: Path) -> Path:
    """(png, 길이) 목록을 total 길이의 mp4 세그먼트로 인코딩한다(_render_static_segment 와 같은 인코더)."""
    from ai_worker.renderer._encode import _resolve_codec, _get_encoder_args
    items = [(Path(p), max(0.001, float(d))) for p, d in timeline if d > 0.0005]
    if not items:
        raise ValueError("empty hook timeline")
    # 합계를 total 에 맞춘다 (마지막 장면이 오차 흡수)
    acc = sum(d for _, d in items[:-1])
    items[-1] = (items[-1][0], max(0.001, total - acc))
    lst = out_path.with_suffix(".ffconcat")
    lines = ["ffconcat version 1.0"]
    for p, d in items:
        lines.append(f"file '{p.resolve()}'")
        lines.append(f"duration {d:.4f}")
    lines.append(f"file '{items[-1][0].resolve()}'")   # concat demuxer 마지막 항목 규칙
    lst.write_text("\n".join(lines) + "\n", encoding="utf-8")
    codec = _resolve_codec()
    cmd = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
        "-vf", f"fps=30,tpad=stop_mode=clone:stop_duration={total:.3f}",
        "-t", f"{total:.3f}",
        *_get_encoder_args(codec),
        "-vsync", "cfr", "-r", "30", "-an", str(out_path),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    lst.unlink(missing_ok=True)
    if r.returncode != 0:
        logger.error("[hook] 타임라인 인코딩 실패:\n%s", r.stderr[-1500:])
        raise subprocess.CalledProcessError(r.returncode, cmd)
    return out_path
