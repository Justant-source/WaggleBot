"""ai_worker/renderer/_frames.py — PIL 프레임 렌더링 함수 (internal)

와글 브랜드 디자인 v3:
  - 옐로우 헤더 #FBD024 + 코드 드로잉 (base_layout.png 불필요)
  - 제목블록: 굵은 검정 제목 + 메타줄 + 구분선
  - 자막: 굵은 검정 #161616, 흐림 없음, 위로 누적
  - 미디어: 자연비율 contain (좌우 흰여백)
  - 아웃트로: 마스코트 + 참여 유도 질문 + 댓글입력 목업
  - 댓글씬: 아바타·닉네임·BEST·추천수 세로 리스트
"""

import datetime
import hashlib
import logging
import shutil
from pathlib import Path
from typing import Optional

import requests
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 비디오 텍스트 오버레이 PNG 캐시 (process 내 유효, 재시작 시 자동 초기화)
# ---------------------------------------------------------------------------
_overlay_cache: dict[str, Path] = {}

# 캔버스 기본 상수 (layout.json 미로드 시 fallback)
CANVAS_W = 1080
CANVAS_H = 1920
HEADER_H = 150
HEADER_COLOR = "#FBD024"


# ---------------------------------------------------------------------------
# 이미지 유틸리티
# ---------------------------------------------------------------------------

_dc_session: requests.Session | None = None


def _get_dc_session() -> requests.Session:
    """DCInside 이미지 다운로드용 세션 (쿠키 워밍업 포함)."""
    global _dc_session
    if _dc_session is not None:
        return _dc_session
    _dc_session = requests.Session()
    _dc_session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/131.0.0.0 Safari/537.36",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    })
    try:
        _dc_session.get("https://www.dcinside.com/", timeout=10)
        logger.debug("DCInside 이미지 세션 워밍업 OK (cookies=%d)",
                     len(_dc_session.cookies))
    except Exception:
        logger.debug("DCInside 이미지 세션 워밍업 실패 — 쿠키 없이 시도")
    return _dc_session


def _load_image(
    src: str, cache_dir: Path, max_retries: int = 2,
) -> Optional[Image.Image]:
    """URL 또는 로컬 경로에서 이미지 로드. 실패 시 재시도 후 None."""
    if src.startswith("http://") or src.startswith("https://"):
        url_hash = hashlib.md5(src.encode()).hexdigest()[:16]
        cache_path = cache_dir / f"img_{url_hash}.jpg"
        if not cache_path.exists():
            for attempt in range(max_retries + 1):
                try:
                    if "dcinside.com" in src:
                        sess = _get_dc_session()
                        resp = sess.get(src, timeout=15, headers={
                            "Referer": "https://gall.dcinside.com/",
                            "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
                            "Sec-Fetch-Dest": "image",
                            "Sec-Fetch-Mode": "no-cors",
                            "Sec-Fetch-Site": "cross-site",
                        })
                    else:
                        _hdrs = {
                            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                                          "Chrome/131.0.0.0 Safari/537.36",
                            "Referer": f"{src.split('/')[0]}//{src.split('/')[2]}/",
                            "Accept": "image/*,*/*;q=0.8",
                        }
                        resp = requests.get(src, timeout=15, headers=_hdrs)
                    resp.raise_for_status()
                    if len(resp.content) < 200:
                        logger.warning(
                            "이미지 크기 의심 (%d bytes, 플레이스홀더?): %s",
                            len(resp.content), src,
                        )
                        return None
                    cache_path.write_bytes(resp.content)
                    break
                except Exception as e:
                    if attempt < max_retries:
                        import time
                        time.sleep(1 * (attempt + 1))
                        logger.debug(
                            "이미지 다운로드 재시도 (%d/%d): %s",
                            attempt + 1, max_retries, src,
                        )
                    else:
                        logger.warning(
                            "이미지 다운로드 실패 (재시도 %d회 후): %s — %s",
                            max_retries, src, e,
                        )
                        return None
        try:
            return Image.open(cache_path).convert("RGB")
        except Exception as e:
            logger.warning("이미지 열기 실패: %s — %s", cache_path, e)
            return None
    try:
        return Image.open(src).convert("RGB")
    except Exception as e:
        logger.warning("로컬 이미지 로드 실패: %s — %s", src, e)
        return None


def _fit_cover(img: Image.Image, w: int, h: int) -> Image.Image:
    """Cover 모드: 비율 유지 + 중앙 크롭."""
    iw, ih = img.size
    scale = max(w / iw, h / ih)
    nw, nh = int(iw * scale), int(ih * scale)
    img = img.resize((nw, nh), Image.LANCZOS)
    left = (nw - w) // 2
    top = (nh - h) // 2
    return img.crop((left, top, left + w, top + h))


def _fit_contain(img: Image.Image, max_w: int, max_h: int) -> Image.Image:
    """Contain 모드: 비율 유지, 최대 크기 이하로 리사이즈 (크롭 없음, 흰여백)."""
    iw, ih = img.size
    if iw == 0 or ih == 0:
        return img
    scale = min(max_w / iw, max_h / ih)
    nw, nh = max(1, int(iw * scale)), max(1, int(ih * scale))
    return img.resize((nw, nh), Image.LANCZOS)


def _paste_rounded(
    base: Image.Image, overlay: Image.Image,
    x: int, y: int, radius: int,
) -> Image.Image:
    """둥근 모서리 마스크로 overlay를 base에 붙여넣기."""
    w, h = overlay.size
    mask = Image.new("L", (w, h), 0)
    md = ImageDraw.Draw(mask)
    try:
        md.rounded_rectangle([(0, 0), (w - 1, h - 1)], radius=radius, fill=255)
    except AttributeError:
        md.rectangle([(0, 0), (w - 1, h - 1)], fill=255)
    base = base.convert("RGBA")
    ov = overlay.convert("RGBA")
    ov.putalpha(mask)
    base.paste(ov, (x, y), ov)
    return base.convert("RGB")


def _truncate(text: str, max_chars: int) -> str:
    """max_chars 초과 시 (max_chars-2)자 + '..'."""
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 2] + ".."


def _font_w(font: ImageFont.FreeTypeFont, text: str) -> float:
    """폰트 기준 텍스트 픽셀 너비 (PIL 버전 호환)."""
    try:
        return font.getlength(text)
    except AttributeError:
        return float(font.getbbox(text)[2])


def _wrap_korean(
    text: str,
    font: ImageFont.FreeTypeFont,
    max_width: int,
    keep_all: bool = False,
) -> list[str]:
    """한글 텍스트 줄바꿈 — 단어(공백) 단위 우선.

    keep_all=True: 단어 내 강제분리 없음 (어절 단위 유지, 제목·댓글용).
    keep_all=False: 긴 단어는 글자 단위 강제 분리 (기본값).
    """
    if _font_w(font, text) <= max_width:
        return [text]

    words = text.split(" ")
    lines: list[str] = []
    current = ""

    for word in words:
        candidate = f"{current} {word}" if current else word
        if _font_w(font, candidate) <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            if not keep_all and _font_w(font, word) > max_width:
                # 글자 단위 강제 분리
                for ch in word:
                    if current and _font_w(font, current + ch) > max_width:
                        lines.append(current)
                        current = ch
                    else:
                        current = (current or "") + ch
            else:
                current = word

    if current.strip():
        lines.append(current.rstrip())
    return lines or [text]


def _draw_centered_text(
    draw: ImageDraw.ImageDraw,
    lines: list[str],
    font: ImageFont.FreeTypeFont,
    y_start: int,
    line_height: int,
    color: str,
    canvas_w: int,
    stroke_color: str = "",
    stroke_width: int = 0,
) -> int:
    """줄 목록을 중앙 정렬로 그리고, 마지막 줄 아래 y를 반환한다."""
    y = y_start
    for line in lines:
        cx = int((canvas_w - _font_w(font, line)) / 2)
        if stroke_color and stroke_width > 0:
            draw.text((cx, y), line, font=font, fill=color,
                      stroke_width=stroke_width, stroke_fill=stroke_color)
        else:
            draw.text((cx, y), line, font=font, fill=color)
        y += line_height
    return y


# ---------------------------------------------------------------------------
# 포맷 헬퍼
# ---------------------------------------------------------------------------

def _fmt_count(val: int | str | None) -> str:
    """숫자를 한국식 약식으로 포맷. 14500 → '1.4만', 10000 → '1만', 1200 → '1.2천'."""
    if val is None:
        return ""
    try:
        n = int(val)
    except (ValueError, TypeError):
        return str(val)
    if n >= 10_000:
        x = n / 10_000
        return f"{int(x)}만" if x == int(x) else f"{x:.1f}만"
    if n >= 1_000:
        x = n / 1_000
        return f"{int(x)}천" if x == int(x) else f"{x:.1f}천"
    return str(n)


def _relative_time(dt: datetime.datetime | None) -> str:
    """datetime → '3시간 전' 형식 상대 시간 문자열. None이면 ''."""
    if dt is None:
        return ""
    try:
        now = datetime.datetime.now(dt.tzinfo)
        diff = now - dt
        seconds = int(diff.total_seconds())
        if seconds < 0:
            return ""
        if seconds < 60:
            return "방금 전"
        minutes = seconds // 60
        if minutes < 60:
            return f"{minutes}분 전"
        hours = minutes // 60
        if hours < 24:
            return f"{hours}시간 전"
        days = hours // 24
        if days < 30:
            return f"{days}일 전"
        months = days // 30
        if months < 12:
            return f"{months}개월 전"
        return f"{days // 365}년 전"
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# 헤더 + 제목블록 드로잉 (공통 컴포넌트)
# ---------------------------------------------------------------------------

def _draw_header(
    draw: ImageDraw.ImageDraw,
    layout: dict,
    font_dir: Path,
) -> None:
    """옐로우 와글 헤더바 + 셰브론(‹) + 채널명 + 햄버거(≡)를 그린다."""
    from ai_worker.renderer.layout import _load_font

    g = layout["global"]
    hdr = g["header"]
    cw = layout["canvas"]["width"]

    h = hdr.get("height", 150)
    bg = hdr.get("bg_color", "#FBD024")
    ink = hdr.get("ink_color", "#1A1A1A")
    channel = hdr.get("channel_name", "와글")
    title_fs = hdr.get("title_font_size", 52)
    stroke = hdr.get("icon_stroke", 6)

    # 배경
    draw.rectangle([(0, 0), (cw, h)], fill=bg)

    cy = h // 2

    # 셰브론 (‹) — 좌측 아이콘
    arm = 28
    tip_x = 52
    draw.line(
        [(tip_x + arm, cy - arm), (tip_x, cy), (tip_x + arm, cy + arm)],
        fill=ink, width=stroke,
    )

    # 채널명 — 수평 중앙
    font = _load_font(font_dir, "NotoSansKR-Bold.ttf", title_fs)
    tw = int(_font_w(font, channel))
    tx = (cw - tw) // 2
    ty = (h - title_fs) // 2 - 2
    draw.text((tx, ty), channel, font=font, fill=ink)

    # 햄버거 (≡) — 우측
    mx = cw - 96
    line_len = 52
    for i in (-1, 0, 1):
        my = cy + i * 18
        draw.line([(mx, my), (mx + line_len, my)], fill=ink, width=stroke)


def _draw_title_block(
    draw: ImageDraw.ImageDraw,
    layout: dict,
    title: str,
    font_dir: Path,
    meta: dict | None = None,
) -> int:
    """제목블록(제목+메타+구분선)을 그리고 콘텐츠 시작 Y를 반환한다.

    meta: {"author":str, "time":str, "views":str, "comments":int|str}
    각 필드가 비어있으면 해당 절을 생략한다.
    """
    from ai_worker.renderer.layout import _load_font

    g = layout["global"]
    hdr = g["header"]
    tb = g["title_block"]
    meta_cfg = tb.get("meta", {})
    divider_cfg = tb.get("divider", {})
    cw = layout["canvas"]["width"]

    header_h: int = hdr.get("height", 150)
    pad_top: int = tb.get("pad_top", 32)
    pad_x: int = tb.get("pad_x", 44)
    font_size: int = tb.get("font_size", 50)
    line_h: int = tb.get("line_height", 62)
    max_lines: int = tb.get("max_lines", 2)
    title_color: str = tb.get("color", "#161616")

    meta_gap: int = meta_cfg.get("gap_top", 16)
    meta_fs: int = meta_cfg.get("font_size", 28)
    meta_color: str = meta_cfg.get("color", "#9C9C9C")
    sep: str = meta_cfg.get("sep", " │ ")
    author_fallback: str = meta_cfg.get("author_fallback", "와글")

    divider_gap: int = divider_cfg.get("gap_top", 20)
    divider_th: int = divider_cfg.get("thickness", 2)
    divider_color: str = divider_cfg.get("color", "#E7E7E7")

    content_gap: int = g.get("content", {}).get("gap_top", 28)

    # ── 제목 ──────────────────────────────────────────────────────────────
    font = _load_font(font_dir, "NotoSansKR-Bold.ttf", font_size)
    max_w = cw - 2 * pad_x
    wrapped = _wrap_korean(title, font, max_w, keep_all=True)
    n_lines = min(len(wrapped), max_lines)

    y = header_h + pad_top
    for line in wrapped[:n_lines]:
        draw.text((pad_x, y), line, font=font, fill=title_color)
        y += line_h
    title_bottom = y

    # ── 메타줄 ────────────────────────────────────────────────────────────
    meta_font = _load_font(font_dir, "NotoSansKR-Medium.ttf", meta_fs)
    meta_lh = int(meta_fs * 1.35)
    y_meta = title_bottom + meta_gap

    if meta:
        parts: list[str] = []
        author = (meta.get("author") or "").strip() or author_fallback
        parts.append(author)

        t = (meta.get("time") or "").strip()
        if t:
            parts.append(t)

        v = (meta.get("views") or "").strip()
        if v and v != "0":
            parts.append(f"조회 {v}")

        c = meta.get("comments")
        if c:
            c_str = _fmt_count(c)
            if c_str and c_str != "0":
                parts.append(f"댓글 {c_str}")

        meta_text = sep.join(parts)
    else:
        meta_text = author_fallback

    draw.text((pad_x, y_meta), meta_text, font=meta_font, fill=meta_color)
    y_meta_bottom = y_meta + meta_lh

    # ── 구분선 ────────────────────────────────────────────────────────────
    y_div = y_meta_bottom + divider_gap
    draw.rectangle([(0, y_div), (cw, y_div + divider_th)], fill=divider_color)

    content_y = y_div + divider_th + content_gap
    return int(content_y)


def _title_block_bottom_y(
    layout: dict,
    title: str,
    font_dir: Path,
) -> int:
    """제목블록 아래쪽 콘텐츠 시작 Y를 순수 계산으로 반환한다.

    PIL 드로잉 없이 좌표만 계산 — 모든 씬 렌더러가 공유하는 린치핀.
    """
    from ai_worker.renderer.layout import _load_font

    g = layout["global"]
    hdr = g["header"]
    tb = g["title_block"]
    meta_cfg = tb.get("meta", {})
    divider_cfg = tb.get("divider", {})
    cw = layout["canvas"]["width"]

    header_h: int = hdr.get("height", 150)
    pad_top: int = tb.get("pad_top", 32)
    pad_x: int = tb.get("pad_x", 44)
    font_size: int = tb.get("font_size", 50)
    line_h: int = tb.get("line_height", 62)
    max_lines: int = tb.get("max_lines", 2)

    meta_gap: int = meta_cfg.get("gap_top", 16)
    meta_fs: int = meta_cfg.get("font_size", 28)

    divider_gap: int = divider_cfg.get("gap_top", 20)
    divider_th: int = divider_cfg.get("thickness", 2)
    content_gap: int = g.get("content", {}).get("gap_top", 28)

    # 제목 줄 수
    font = _load_font(font_dir, "NotoSansKR-Bold.ttf", font_size)
    max_w = cw - 2 * pad_x
    wrapped = _wrap_korean(title, font, max_w, keep_all=True)
    n_lines = min(len(wrapped), max_lines)

    title_bottom = header_h + pad_top + n_lines * line_h
    meta_bottom = title_bottom + meta_gap + int(meta_fs * 1.35)
    div_bottom = meta_bottom + divider_gap + divider_th
    content_y = div_bottom + content_gap

    return int(content_y)


# ---------------------------------------------------------------------------
# 베이스 프레임 생성
# ---------------------------------------------------------------------------

def _create_base_frame(
    layout: dict,
    title: str,
    font_dir: Path,
    assets_dir: Path,
    meta: dict | None = None,
) -> Image.Image:
    """와글 베이스 프레임: 흰 캔버스 + 옐로우 헤더바 + 제목블록 코드 드로잉.

    assets_dir는 하위 호환용 파라미터(현재 미사용).
    모든 씬 렌더러가 이 프레임을 .copy()해서 사용한다.
    """
    g = layout["global"]
    cw = layout["canvas"]["width"]
    ch = layout["canvas"]["height"]

    base = Image.new("RGB", (cw, ch), g.get("background_color", "#FFFFFF"))
    draw = ImageDraw.Draw(base)

    _draw_header(draw, layout, font_dir)
    _draw_title_block(draw, layout, title, font_dir, meta=meta)

    return base


def _create_header_only_frame(
    layout: dict,
    font_dir: Path,
) -> Image.Image:
    """헤더바만 있는 프레임 (아웃트로용 — 제목블록 없음)."""
    g = layout["global"]
    cw = layout["canvas"]["width"]
    ch = layout["canvas"]["height"]

    base = Image.new("RGB", (cw, ch), g.get("background_color", "#FFFFFF"))
    draw = ImageDraw.Draw(base)
    _draw_header(draw, layout, font_dir)
    return base


# ---------------------------------------------------------------------------
# 씬 렌더러 (모두 base_frame.copy()에서 시작)
# ---------------------------------------------------------------------------

def _render_intro_frame(
    base_frame: Image.Image,
    img_pil: Optional[Image.Image],
    hook_text: str,
    layout: dict,
    font_dir: Path,
    out_path: Path,
    content_top: int,
) -> Path:
    """씬 intro — hook 자막(중앙, 굵은 검정) + 자연비율 표지 이미지."""
    from ai_worker.renderer.layout import _load_font

    sc = layout["scenes"]["intro"]
    cap_cfg = sc.get("caption", {})
    media_cfg = sc.get("media", {})
    cw = layout["canvas"]["width"]
    ch = layout["canvas"]["height"]

    cap_fs: int = cap_cfg.get("font_size", 50)
    cap_lh: int = cap_cfg.get("line_height", 62)
    cap_color: str = cap_cfg.get("color", "#161616")
    cap_pad_top: int = cap_cfg.get("pad_top", 56)
    cap_max_w: int = cap_cfg.get("max_width", 900)
    cap_max_lines: int = cap_cfg.get("max_lines", 2)

    media_max_w: int = media_cfg.get("max_width", 820)
    media_gap: int = media_cfg.get("gap_top", 56)
    media_radius: int = media_cfg.get("radius", 8)

    font = _load_font(font_dir, "NotoSansKR-Bold.ttf", cap_fs)
    img = base_frame.copy()
    draw = ImageDraw.Draw(img)

    # 자막 (위)
    cap_y = content_top + cap_pad_top
    cap_bottom = cap_y
    if hook_text:
        lines = _wrap_korean(hook_text, font, cap_max_w)[:cap_max_lines]
        _draw_centered_text(draw, lines, font, cap_y, cap_lh, cap_color, cw)
        cap_bottom = cap_y + len(lines) * cap_lh

    # 미디어 (자연비율 contain, 중앙 배치)
    media_y = cap_bottom + media_gap
    if img_pil is not None:
        max_h = max(100, ch - media_y - 60)
        fitted = _fit_contain(img_pil, media_max_w, max_h)
        nw, nh = fitted.size
        mx = (cw - nw) // 2
        img = _paste_rounded(img, fitted, mx, media_y, media_radius)
    else:
        ph_h = min(820, ch - media_y - 60)
        draw2 = ImageDraw.Draw(img)
        _draw_media_placeholder(draw2, cw // 2 - media_max_w // 2, media_y,
                                media_max_w, ph_h, media_radius)

    img.save(str(out_path), "PNG")
    return out_path


def _render_image_text_frame(
    base_frame: Image.Image,
    img_pil: Optional[Image.Image],
    text: str,
    layout: dict,
    font_dir: Path,
    out_path: Path,
    content_top: int,
) -> Path:
    """씬 image_text — 자막(위) + 자연비율 이미지(좌우 흰여백)."""
    from ai_worker.renderer.layout import _load_font

    sc = layout["scenes"]["image_text"]
    cap_cfg = sc.get("caption_above", {})
    media_cfg = sc.get("media", {})
    cw = layout["canvas"]["width"]
    ch = layout["canvas"]["height"]

    cap_fs: int = cap_cfg.get("font_size", 50)
    cap_lh: int = cap_cfg.get("line_height", 62)
    cap_color: str = cap_cfg.get("color", "#161616")
    cap_pad_top: int = cap_cfg.get("pad_top", 56)
    cap_max_w: int = cap_cfg.get("max_width", 900)
    cap_max_lines: int = cap_cfg.get("max_lines", 2)

    media_max_w: int = media_cfg.get("max_width", 820)
    media_gap: int = media_cfg.get("gap_top", 48)
    media_radius: int = media_cfg.get("radius", 8)

    font = _load_font(font_dir, "NotoSansKR-Bold.ttf", cap_fs)
    img = base_frame.copy()
    draw = ImageDraw.Draw(img)

    # 자막 (위)
    cap_y = content_top + cap_pad_top
    lines = _wrap_korean(text, font, cap_max_w)[:cap_max_lines]
    if lines:
        _draw_centered_text(draw, lines, font, cap_y, cap_lh, cap_color, cw)
    cap_bottom = cap_y + len(lines) * cap_lh

    # 미디어 (자연비율 contain)
    media_y = cap_bottom + media_gap
    if img_pil is not None:
        max_h = max(100, ch - media_y - 60)
        fitted = _fit_contain(img_pil, media_max_w, max_h)
        nw, nh = fitted.size
        mx = (cw - nw) // 2
        img = _paste_rounded(img, fitted, mx, media_y, media_radius)
    else:
        ph_h = min(820, ch - media_y - 60)
        draw2 = ImageDraw.Draw(img)
        _draw_media_placeholder(draw2, cw // 2 - media_max_w // 2, media_y,
                                media_max_w, ph_h, media_radius)

    img.save(str(out_path), "PNG")
    return out_path


def _render_text_only_frame(
    base_frame: Image.Image,
    text_history: list[dict],
    layout: dict,
    font_dir: Path,
    out_path: Path,
    content_top: int,
) -> Path:
    """씬 text_only — 굵은 검정 자막 누적, 흐림·시안 댓글 분기 제거."""
    from ai_worker.renderer.layout import _load_font

    sc = layout["scenes"]["text_only"]
    ta = sc["elements"]["text_area"]

    font_size: int = ta.get("font_size", 50)
    lh: int = ta.get("line_height", 71)
    slot_gap: int = ta.get("slot_gap", 45)
    color: str = ta.get("color", "#161616")
    pad_top: int = ta.get("pad_top", 96)

    font = _load_font(font_dir, "NotoSansKR-Bold.ttf", font_size)
    cw = layout["canvas"]["width"]

    img = base_frame.copy()
    draw = ImageDraw.Draw(img)

    y = content_top + pad_top
    for entry_i, entry in enumerate(text_history):
        if entry_i > 0:
            y += slot_gap  # 슬롯 간 간격 (첫 슬롯 제외)
        for line_text in entry.get("lines", []):
            cx = int((cw - _font_w(font, line_text)) / 2)
            draw.text((cx, y), line_text, font=font, fill=color)
            y += lh

    img.save(str(out_path), "PNG")
    return out_path


def _render_image_only_frame(
    base_frame: Image.Image,
    img_pil: Optional[Image.Image],
    layout: dict,
    out_path: Path,
    content_top: int,
) -> Path:
    """씬 image_only — 자연비율 이미지 중앙 배치."""
    sc = layout["scenes"]["image_only"]
    media_cfg = sc.get("media", {})
    cw = layout["canvas"]["width"]
    ch = layout["canvas"]["height"]

    media_max_w: int = media_cfg.get("max_width", 820)
    media_pad_top: int = media_cfg.get("pad_top", 80)
    media_radius: int = media_cfg.get("radius", 8)

    media_y = content_top + media_pad_top
    img = base_frame.copy()

    if img_pil is not None:
        max_h = max(100, ch - media_y - 60)
        fitted = _fit_contain(img_pil, media_max_w, max_h)
        nw, nh = fitted.size
        mx = (cw - nw) // 2
        img = _paste_rounded(img, fitted, mx, media_y, media_radius)
    else:
        ph_h = min(900, ch - media_y - 60)
        draw = ImageDraw.Draw(img)
        _draw_media_placeholder(draw, cw // 2 - media_max_w // 2, media_y,
                                media_max_w, ph_h, media_radius)

    img.save(str(out_path), "PNG")
    return out_path


def _render_outro_frame(
    header_only_frame: Image.Image,
    overlay_text: str,
    layout: dict,
    font_dir: Path,
    out_path: Path,
) -> Path:
    """씬 outro — 마스코트 + 참여유도 질문 + 댓글입력 목업 (구독유도 없음).

    header_only_frame을 베이스로 사용 (제목블록 없음).
    """
    from ai_worker.renderer.layout import _load_font

    sc = layout["scenes"]["outro"]
    mascot_cfg = sc.get("mascot", {})
    q_cfg = sc.get("question", {})
    sub_cfg = sc.get("sub_caption", {})
    box_cfg = sc.get("input_box", {})
    cta_cfg = sc.get("cta_text", {})

    g = layout["global"]
    hdr = g["header"]
    cw = layout["canvas"]["width"]
    ch = layout["canvas"]["height"]
    hdr_h: int = hdr.get("height", 150)
    hdr_bg: str = hdr.get("bg_color", "#FBD024")
    hdr_ink: str = hdr.get("ink_color", "#1A1A1A")

    img = header_only_frame.copy()
    draw = ImageDraw.Draw(img)

    # ── 마스코트 (코드 드로잉) ────────────────────────────────────────────
    mascot_d: int = mascot_cfg.get("diameter", 220)
    mascot_color: str = mascot_cfg.get("circle_color", "#1A1A1A")
    feature_color: str = mascot_cfg.get("feature_color", "#FBD024")
    mascot_pad: int = mascot_cfg.get("pad_top", 180)

    mx0 = (cw - mascot_d) // 2
    my0 = hdr_h + mascot_pad
    mx1 = mx0 + mascot_d
    my1 = my0 + mascot_d
    draw.ellipse([(mx0, my0), (mx1, my1)], fill=mascot_color)

    # 눈 — 두 옐로우 타원
    eye_w = int(mascot_d * 0.12)
    eye_h = int(mascot_d * 0.17)
    eye_cy = my0 + int(mascot_d * 0.38)
    eye_gap = int(mascot_d * 0.19)
    mcx = (mx0 + mx1) // 2
    for ex in [mcx - eye_gap - eye_w // 2, mcx + eye_gap - eye_w // 2]:
        draw.ellipse([(ex, eye_cy - eye_h // 2),
                      (ex + eye_w, eye_cy + eye_h // 2)],
                     fill=feature_color)

    # 입 — 호
    mouth_w = int(mascot_d * 0.24)
    mouth_h = int(mascot_d * 0.10)
    mouth_y = my0 + int(mascot_d * 0.60)
    mx0m = mcx - mouth_w // 2
    draw.arc(
        [(mx0m, mouth_y), (mx0m + mouth_w, mouth_y + mouth_h)],
        start=0, end=180, fill=feature_color, width=5,
    )

    y = my1  # 마스코트 아래부터

    # ── 큰 질문 자막 ──────────────────────────────────────────────────────
    q_fs: int = q_cfg.get("font_size", 62)
    q_color: str = q_cfg.get("color", "#161616")
    q_gap: int = q_cfg.get("gap_top", 60)
    q_max_w: int = q_cfg.get("max_width", 900)
    q_lh: int = q_cfg.get("line_height", 78)

    q_font = _load_font(font_dir, "NotoSansKR-Bold.ttf", q_fs)
    question = overlay_text.strip() or "여러분이라면 어떻게 하셨을까요?"
    q_lines = _wrap_korean(question, q_font, q_max_w)
    q_y = y + q_gap
    _draw_centered_text(draw, q_lines, q_font, q_y, q_lh, q_color, cw)
    y = q_y + len(q_lines) * q_lh

    # ── 서브 캡션 ─────────────────────────────────────────────────────────
    sub_text: str = sub_cfg.get("text", "생각을 댓글로 남겨주세요")
    sub_fs: int = sub_cfg.get("font_size", 36)
    sub_color: str = sub_cfg.get("color", "#7A7A7A")
    sub_gap: int = sub_cfg.get("gap_top", 40)

    sub_font = _load_font(font_dir, "NotoSansKR-Medium.ttf", sub_fs)
    sub_x = (cw - int(_font_w(sub_font, sub_text))) // 2
    sub_y = y + sub_gap
    draw.text((sub_x, sub_y), sub_text, font=sub_font, fill=sub_color)
    y = sub_y + int(sub_fs * 1.35)

    # ── 댓글 입력창 목업 ──────────────────────────────────────────────────
    box_w: int = box_cfg.get("width", 860)
    box_h: int = box_cfg.get("height", 88)
    box_bg: str = box_cfg.get("bg", "#F2F2F2")
    box_border: str = box_cfg.get("border", "#E7E7E7")
    av_label: str = box_cfg.get("avatar_label", "나")
    av_size: int = box_cfg.get("avatar_size", 64)
    placeholder: str = box_cfg.get("placeholder", "댓글 추가...")
    ph_color: str = box_cfg.get("placeholder_color", "#9C9C9C")
    box_gap: int = box_cfg.get("gap_top", 56)

    box_x = (cw - box_w) // 2
    box_y = y + box_gap
    box_r = box_h // 2  # pill 형태

    try:
        draw.rounded_rectangle(
            [(box_x, box_y), (box_x + box_w, box_y + box_h)],
            radius=box_r, fill=box_bg, outline=box_border, width=2,
        )
    except TypeError:
        # older PIL: rounded_rectangle doesn't support outline+width
        try:
            draw.rounded_rectangle(
                [(box_x, box_y), (box_x + box_w, box_y + box_h)],
                radius=box_r, fill=box_bg,
            )
        except AttributeError:
            draw.rectangle(
                [(box_x, box_y), (box_x + box_w, box_y + box_h)],
                fill=box_bg,
            )

    # 아바타 (옐로우 원 + 글자)
    av_margin = (box_h - av_size) // 2
    av_x0 = box_x + av_margin + 8
    av_y0 = box_y + av_margin
    draw.ellipse(
        [(av_x0, av_y0), (av_x0 + av_size, av_y0 + av_size)],
        fill=hdr_bg,
    )
    av_font = _load_font(font_dir, "NotoSansKR-Bold.ttf", int(av_size * 0.45))
    ax = av_x0 + (av_size - int(_font_w(av_font, av_label))) // 2
    ay = av_y0 + int(av_size * 0.25)
    draw.text((ax, ay), av_label, font=av_font, fill=hdr_ink)

    # 플레이스홀더
    ph_x = av_x0 + av_size + 20
    ph_fs = int(box_h * 0.35)
    ph_font = _load_font(font_dir, "NotoSansKR-Regular.ttf", ph_fs)
    ph_y = box_y + (box_h - ph_fs) // 2 - 2
    draw.text((ph_x, ph_y), placeholder, font=ph_font, fill=ph_color)

    # 전송 화살표 (삼각형)
    arr_r = int(box_h * 0.25)
    arr_cx = box_x + box_w - av_margin - arr_r - 8
    arr_cy = box_y + box_h // 2
    draw.polygon([
        (arr_cx - arr_r, arr_cy - arr_r),
        (arr_cx - arr_r, arr_cy + arr_r),
        (arr_cx + arr_r, arr_cy),
    ], fill="#C9C9C9")

    y = box_y + box_h

    # ── CTA ───────────────────────────────────────────────────────────────
    cta_text: str = cta_cfg.get("text", "↓ 댓글 창에서 의견 나눠요")
    cta_fs: int = cta_cfg.get("font_size", 30)
    cta_color: str = cta_cfg.get("color", "#7A7A7A")
    cta_gap: int = cta_cfg.get("gap_top", 36)

    cta_font = _load_font(font_dir, "NotoSansKR-Medium.ttf", cta_fs)
    cta_x = (cw - int(_font_w(cta_font, cta_text))) // 2
    cta_y = y + cta_gap
    draw.text((cta_x, cta_y), cta_text, font=cta_font, fill=cta_color)

    img.save(str(out_path), "PNG")
    return out_path


def _render_comments_frame(
    base_frame: Image.Image,
    comment_items: list[dict],
    layout: dict,
    font_dir: Path,
    out_path: Path,
    content_top: int,
    reveal_count: int | None = None,
) -> Path:
    """씬 comments — 정렬바 + 커뮤니티 댓글 세로 리스트.

    comment_items: [{"author":str, "content":str, "likes":int, "is_best":bool}]
    reveal_count: 누적 공개 개수(1~N). None이면 전체 표시(레거시 동작).
    """
    from ai_worker.renderer.layout import _load_font

    sc = layout["scenes"]["comments"]
    sort_cfg = sc.get("sort_bar", {})
    row_cfg = sc.get("row", {})
    badge_cfg = row_cfg.get("best_badge", {})

    cw = layout["canvas"]["width"]
    ch = layout["canvas"]["height"]

    # 폰트 로드
    sort_fs: int = sort_cfg.get("font_size", 34)
    nick_size: int = row_cfg.get("nick_size", 29)
    text_size: int = row_cfg.get("text_size", 33)
    footer_fs: int = row_cfg.get("footer_font_size", 26)
    badge_fs: int = badge_cfg.get("font_size", 22)
    av_d: int = row_cfg.get("avatar_d", 64)

    sort_font = _load_font(font_dir, "NotoSansKR-Bold.ttf", sort_fs)
    sort_label_font = _load_font(font_dir, "NotoSansKR-Medium.ttf", sort_fs - 4)
    nick_font = _load_font(font_dir, "NotoSansKR-Bold.ttf", nick_size)
    text_font = _load_font(font_dir, "NotoSansKR-Medium.ttf", text_size)
    footer_font = _load_font(font_dir, "NotoSansKR-Regular.ttf", footer_fs)
    badge_font = _load_font(font_dir, "NotoSansKR-Bold.ttf", badge_fs)

    pad_x: int = row_cfg.get("pad_x", 44)
    av_gap: int = row_cfg.get("avatar_gap", 20)
    nick_lh: int = int(nick_size * 1.35)
    text_lh: int = int(text_size * 1.35)
    text_max_lines: int = row_cfg.get("text_max_lines", 3)
    footer_lh: int = int(footer_fs * 1.35)
    nick_color: str = row_cfg.get("nick_color", "#161616")
    text_color: str = row_cfg.get("text_color", "#161616")
    footer_color: str = row_cfg.get("footer_color", "#9C9C9C")
    divider_color: str = row_cfg.get("divider", "#E7E7E7")
    divider_th: int = max(1, int(row_cfg.get("divider_thickness", 1)))
    row_pad_top: int = row_cfg.get("row_pad_top", 28)
    row_pad_bot: int = row_cfg.get("row_pad_bot", 28)

    badge_bg: str = badge_cfg.get("bg", "#FF5436")
    badge_fg: str = badge_cfg.get("fg", "#FFFFFF")
    badge_label: str = badge_cfg.get("label", "BEST")
    badge_px: int = badge_cfg.get("pad_x", 14)
    badge_py: int = badge_cfg.get("pad_y", 4)
    badge_r: int = badge_cfg.get("radius", 6)

    sort_pad_top: int = sort_cfg.get("pad_top", 36)
    sort_pad_x: int = sort_cfg.get("pad_x", 44)
    count_color: str = sort_cfg.get("count_color", "#161616")
    label_color: str = sort_cfg.get("label_color", "#9C9C9C")
    sort_label: str = sort_cfg.get("label", "추천순 ▾")

    # 아바타 색상 팔레트
    _AV_COLORS = [
        "#4A90D9", "#E67E22", "#27AE60", "#9B59B6",
        "#E74C3C", "#1ABC9C", "#F39C12", "#2980B9",
    ]

    img = base_frame.copy()
    draw = ImageDraw.Draw(img)

    # ── 정렬 바 ────────────────────────────────────────────────────────────
    n_total = len(comment_items)
    y = content_top + sort_pad_top

    # "댓글 N" — 왼쪽
    count_text = f"댓글 {n_total}"
    draw.text((sort_pad_x, y), count_text, font=sort_font, fill=count_color)

    # "추천순 ▾" — 오른쪽
    lbl_w = int(_font_w(sort_label_font, sort_label))
    draw.text((cw - sort_pad_x - lbl_w, y), sort_label,
              font=sort_label_font, fill=label_color)

    y += int(sort_fs * 1.4) + 8

    # 구분선
    draw.rectangle([(0, y), (cw, y + divider_th)], fill=divider_color)
    y += divider_th

    # ── 댓글 행 ────────────────────────────────────────────────────────────
    text_x = pad_x + av_d + av_gap
    text_area_w = cw - text_x - pad_x
    av_font_size = max(14, int(av_d * 0.42))

    # 노출 범위 결정 (reveal_count=None이면 전체)
    visible = comment_items if reveal_count is None else comment_items[:reveal_count]

    # 최신 항목이 항상 보이도록 오래된 항목부터 drop (bottom-anchor window)
    def _row_h(item: dict) -> int:
        """댓글 1행의 픽셀 높이 측정 (draw 없이)."""
        content_text = item.get("content", "")
        c_lines = _wrap_korean(content_text, text_font, text_area_w, keep_all=True)
        n_lines = min(len(c_lines), text_max_lines)
        row_inner = nick_lh + 8 + (n_lines * text_lh) + 8 + footer_lh
        return row_pad_top + row_inner + row_pad_bot + divider_th

    heights = [_row_h(it) for it in visible]
    band_h = (ch - 60) - y  # 정렬바 구분선 아래 ~ 하단 여백

    start = 0
    while sum(heights[start:]) > band_h and start < len(visible) - 1:
        start += 1
    draw_items = visible[start:]

    for c_i, item in enumerate(draw_items):
        row_y = y + row_pad_top

        # 아바타 원
        av_color = _AV_COLORS[hash(item.get("author", "") or "") % len(_AV_COLORS)]
        draw.ellipse(
            [(pad_x, row_y), (pad_x + av_d, row_y + av_d)],
            fill=av_color,
        )
        av_char = (item.get("author") or "익")[0]
        av_font = _load_font(font_dir, "NotoSansKR-Bold.ttf", av_font_size)
        ax = pad_x + (av_d - int(_font_w(av_font, av_char))) // 2
        ay = row_y + int(av_d * 0.28)
        draw.text((ax, ay), av_char, font=av_font, fill="#FFFFFF")

        # 닉네임 + BEST 배지
        nick = item.get("author") or "익명"
        draw.text((text_x, row_y), nick, font=nick_font, fill=nick_color)

        if item.get("is_best"):
            nick_w = int(_font_w(nick_font, nick))
            badge_x0 = text_x + nick_w + 16
            badge_label_w = int(_font_w(badge_font, badge_label))
            badge_x1 = badge_x0 + badge_label_w + badge_px * 2
            badge_y0 = row_y + 2
            badge_y1 = badge_y0 + nick_size + badge_py * 2
            try:
                draw.rounded_rectangle(
                    [(badge_x0, badge_y0), (badge_x1, badge_y1)],
                    radius=badge_r, fill=badge_bg,
                )
            except AttributeError:
                draw.rectangle(
                    [(badge_x0, badge_y0), (badge_x1, badge_y1)],
                    fill=badge_bg,
                )
            draw.text(
                (badge_x0 + badge_px, badge_y0 + badge_py),
                badge_label, font=badge_font, fill=badge_fg,
            )

        # 댓글 본문
        content_text = item.get("content", "")
        c_lines = _wrap_korean(content_text, text_font, text_area_w, keep_all=True)
        c_lines = c_lines[:text_max_lines]
        content_y = row_y + nick_lh + 8
        for tl in c_lines:
            draw.text((text_x, content_y), tl, font=text_font, fill=text_color)
            content_y += text_lh

        # 푸터 (추천수 + 답글)
        likes = item.get("likes", 0)
        likes_str = _fmt_count(likes) if (likes or 0) > 0 else "0"
        footer_text = f"▲  {likes_str}    답글"
        footer_y = content_y + 8
        draw.text((text_x, footer_y), footer_text, font=footer_font, fill=footer_color)

        row_bottom = footer_y + footer_lh + row_pad_bot

        # 행 구분선
        draw.rectangle(
            [(0, row_bottom), (cw, row_bottom + divider_th)],
            fill=divider_color,
        )
        y = row_bottom + divider_th

    img.save(str(out_path), "PNG")
    return out_path


# ---------------------------------------------------------------------------
# 채팅 버블 씬 (P5: KakaoTalk 스타일)
# ---------------------------------------------------------------------------

def _render_chat_frame(
    base_frame: Image.Image,
    messages: list[dict],
    layout: dict,
    font_dir: Path,
    out_path: Path,
    content_top: int,
    reveal_count: int | None = None,
) -> Path:
    """카카오톡 스타일 대화 버블 씬.

    messages: [{"sender":str, "text":str, "is_mine":bool}]
      - is_mine=True  → 우측 노란 버블 (#FFE100)
      - is_mine=False → 좌측 회색 버블 + 아바타 + sender 이름
    reveal_count: 누적 공개 개수(1~N). None이면 전체 표시.
    """
    from ai_worker.renderer.layout import _load_font

    sc = layout.get("scenes", {}).get("chat", {})
    bubble_mine_cfg = sc.get("bubble", {}).get("mine", {})
    bubble_other_cfg = sc.get("bubble", {}).get("other", {})

    cw: int = layout["canvas"]["width"]

    side_pad: int  = int(sc.get("side_pad", 40))
    pad_top: int   = int(sc.get("pad_top", 36))
    font_size: int = int(sc.get("font_size", 36))
    line_h: int    = int(sc.get("line_height", 50))
    name_fs: int   = int(sc.get("name_font_size", 27))
    name_color: str = sc.get("name_color", "#9C9C9C")
    av_d: int      = int(sc.get("avatar_d", 54))
    av_gap: int    = int(sc.get("avatar_gap", 14))
    msg_gap: int   = int(sc.get("msg_gap", 10))
    group_gap: int = int(sc.get("group_gap", 28))

    mine_bg: str   = bubble_mine_cfg.get("bg", "#FFE100")
    mine_fg: str   = bubble_mine_cfg.get("text_color", "#1A1A1A")
    mine_r: int    = int(bubble_mine_cfg.get("radius", 18))
    mine_mw: int   = int(bubble_mine_cfg.get("max_width", 680))
    mine_px: int   = int(bubble_mine_cfg.get("pad_x", 26))
    mine_py: int   = int(bubble_mine_cfg.get("pad_y", 16))

    other_bg: str  = bubble_other_cfg.get("bg", "#F2F2F2")
    other_fg: str  = bubble_other_cfg.get("text_color", "#1A1A1A")
    other_r: int   = int(bubble_other_cfg.get("radius", 18))
    other_mw: int  = int(bubble_other_cfg.get("max_width", 620))
    other_px: int  = int(bubble_other_cfg.get("pad_x", 26))
    other_py: int  = int(bubble_other_cfg.get("pad_y", 16))

    font_msg  = _load_font(font_dir, "NotoSansKR-Bold.ttf", font_size)
    font_name = _load_font(font_dir, "NotoSansKR-Medium.ttf", name_fs)

    _AV_PALETTE = [
        "#4A90D9", "#E67E22", "#27AE60", "#9B59B6",
        "#E74C3C", "#1ABC9C", "#F39C12", "#2980B9",
    ]

    bottom_limit: int = CANVAS_H - 80

    # ── bottom-anchor 슬라이딩 윈도우 ──────────────────────────────────────
    visible = messages if reveal_count is None else messages[:reveal_count]

    def _msg_h(msg: dict, prev_s: str | None) -> int:
        """채팅 메시지 1개의 픽셀 높이 측정 (draw 없이)."""
        sender = msg.get("sender") or "상대방"
        text = (msg.get("text") or "").strip()
        is_mine = bool(msg.get("is_mine", False))
        if not text:
            return 0
        inner_w = (mine_mw if is_mine else other_mw) - (mine_px if is_mine else other_px) * 2
        wrapped = _wrap_korean(text, font_msg, inner_w, keep_all=True) or [text[:30]]
        bubble_inner_h = len(wrapped) * line_h
        py = mine_py if is_mine else other_py
        bubble_h = bubble_inner_h + py * 2
        h = 0
        if prev_s is not None and sender != prev_s:
            h += group_gap - msg_gap
        if not is_mine and sender != prev_s:
            h += name_fs + 6
        h += bubble_h + msg_gap
        return h

    heights: list[int] = []
    ps: str | None = None
    for _m in visible:
        heights.append(_msg_h(_m, ps))
        if (_m.get("text") or "").strip():
            ps = _m.get("sender") or "상대방"

    band_h = bottom_limit - (content_top + pad_top)

    start = 0
    while sum(heights[start:]) > band_h and start < len(visible) - 1:
        start += 1
    draw_msgs = visible[start:]

    img = base_frame.copy()
    draw = ImageDraw.Draw(img)

    y: int = content_top + pad_top
    prev_sender: str | None = None  # 윈도우 첫 메시지가 항상 발신자 이름 표시

    for msg in draw_msgs:
        sender: str = msg.get("sender") or "상대방"
        text: str   = (msg.get("text") or "").strip()
        is_mine: bool = bool(msg.get("is_mine", False))

        if not text:
            continue

        # 버블 내부 텍스트 줄바꿈
        inner_w = (mine_mw if is_mine else other_mw) - (mine_px if is_mine else other_px) * 2
        wrapped = _wrap_korean(text, font_msg, inner_w, keep_all=True)
        if not wrapped:
            wrapped = [text[:30]]

        bubble_inner_h = len(wrapped) * line_h
        py = mine_py if is_mine else other_py
        bubble_h = bubble_inner_h + py * 2

        # sender 전환 시 group_gap 추가
        if prev_sender is not None and sender != prev_sender:
            y += group_gap - msg_gap

        # ── 상대방 메시지 (왼쪽) ──────────────────────────────────────────
        if not is_mine:
            # 처음 등장하는 sender 또는 sender 전환 시 이름 표시
            if sender != prev_sender:
                draw.text((side_pad + av_d + av_gap, y), sender,
                          font=font_name, fill=name_color)
                y += name_fs + 6

            # 아바타 원
            av_color = _AV_PALETTE[hash(sender) % len(_AV_PALETTE)]
            draw.ellipse(
                [(side_pad, y), (side_pad + av_d, y + av_d)],
                fill=av_color,
            )
            av_char = sender[0] if sender else "익"
            av_fs   = max(14, int(av_d * 0.44))
            av_font = _load_font(font_dir, "NotoSansKR-Bold.ttf", av_fs)
            draw.text(
                (side_pad + (av_d - int(_font_w(av_font, av_char))) // 2,
                 y + int(av_d * 0.28)),
                av_char, font=av_font, fill="#FFFFFF",
            )

            # 버블 폭: 최장 줄 기준 + 패딩
            max_line_w = int(max((_font_w(font_msg, ln) for ln in wrapped), default=0))
            bw = min(max_line_w + other_px * 2, other_mw)
            bw = max(bw, 80)
            bx = side_pad + av_d + av_gap
            by = y

            if by + bubble_h > bottom_limit:
                break

            try:
                draw.rounded_rectangle([bx, by, bx + bw, by + bubble_h],
                                       radius=other_r, fill=other_bg)
            except AttributeError:
                draw.rectangle([bx, by, bx + bw, by + bubble_h], fill=other_bg)

            ty = by + other_py
            for ln in wrapped:
                draw.text((bx + other_px, ty), ln, font=font_msg, fill=other_fg)
                ty += line_h

            y = by + bubble_h + msg_gap

        # ── 내 메시지 (오른쪽) ────────────────────────────────────────────
        else:
            max_line_w = int(max((_font_w(font_msg, ln) for ln in wrapped), default=0))
            bw = min(max_line_w + mine_px * 2, mine_mw)
            bw = max(bw, 80)
            bx = cw - side_pad - bw
            by = y

            if by + bubble_h > bottom_limit:
                break

            try:
                draw.rounded_rectangle([bx, by, bx + bw, by + bubble_h],
                                       radius=mine_r, fill=mine_bg)
            except AttributeError:
                draw.rectangle([bx, by, bx + bw, by + bubble_h], fill=mine_bg)

            ty = by + mine_py
            for ln in wrapped:
                draw.text((bx + mine_px, ty), ln, font=font_msg, fill=mine_fg)
                ty += line_h

            y = by + bubble_h + msg_gap

        prev_sender = sender

    img.save(str(out_path), "PNG")
    return out_path


# ---------------------------------------------------------------------------
# 비디오 텍스트 오버레이 (P3: content_top 파라미터 추가)
# ---------------------------------------------------------------------------

def _render_video_text_overlay(
    text: str,
    layout: dict,
    font_dir: Path,
    out_png: Path,
    content_top: int = 0,
) -> Path:
    """비디오 자막을 투명 PNG 오버레이로 렌더링한다.

    content_top > 0 이면 새 caption_above 레이아웃 사용 (자막을 위쪽에 배치).
    content_top == 0 이면 구 elements.text_area.y 기반 배치 (P3 전 하위호환).
    동일 (text, cfg, 크기, content_top) 조합은 모듈 레벨 캐시로 재사용.
    """
    from ai_worker.renderer.layout import _load_font

    video_text_cfg = layout.get("scenes", {}).get("video_text", {})
    canvas_cfg = layout.get("canvas", {})
    cache_raw = (
        f"{text}"
        f"|{video_text_cfg}"
        f"|{canvas_cfg.get('width')}x{canvas_cfg.get('height')}"
        f"|ct{content_top}"
        f"|{out_png.suffix}"
    )
    cache_key = hashlib.md5(cache_raw.encode("utf-8")).hexdigest()

    if cache_key in _overlay_cache and _overlay_cache[cache_key].exists():
        cached = _overlay_cache[cache_key]
        if cached != out_png:
            shutil.copy2(cached, out_png)
            logger.debug("오버레이 캐시 히트 → %s (from %s)", out_png.name, cached.name)
        return out_png

    cw = canvas_cfg["width"]
    ch = canvas_cfg["height"]

    overlay = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    if content_top > 0:
        # 새 디자인: caption_above 기반
        cap_cfg = video_text_cfg.get("caption_above", {})
        font_size: int = cap_cfg.get("font_size", 50)
        lh: int = cap_cfg.get("line_height", 62)
        cap_color: str = cap_cfg.get("color", "#161616")
        cap_pad_top: int = cap_cfg.get("pad_top", 56)
        max_w: int = cap_cfg.get("max_width", 900)
        cap_max_lines: int = cap_cfg.get("max_lines", 2)

        font = _load_font(font_dir, "NotoSansKR-Bold.ttf", font_size)
        lines = _wrap_korean(text, font, max_w)[:cap_max_lines]
        y_start = content_top + cap_pad_top
    else:
        # 구 디자인 (P3 전 하위호환): elements.text_area.y 기반
        ta = video_text_cfg.get("elements", {}).get("text_area", {})
        font_size = ta.get("font_size", 50)
        lh = ta.get("line_height", int(font_size * 1.4))
        cap_color = ta.get("color", "#161616")
        max_w = ta.get("max_width", 900)
        cap_max_lines = ta.get("max_lines", 2)

        font = _load_font(font_dir, "NotoSansKR-Bold.ttf", font_size)
        lines = _wrap_korean(text, font, max_w)[:cap_max_lines]
        total_h = len(lines) * lh
        y_start = ta.get("y", 450) - total_h // 2

    _draw_centered_text(draw, lines, font, y_start, lh, cap_color, cw)

    overlay.save(str(out_png), "PNG")
    _overlay_cache[cache_key] = out_png
    logger.debug("오버레이 캐시 저장 (key=%s…): %s", cache_key[:8], out_png.name)
    return out_png


# ---------------------------------------------------------------------------
# 내부 유틸 (비공개)
# ---------------------------------------------------------------------------

def _draw_media_placeholder(
    draw: ImageDraw.ImageDraw,
    x: int, y: int, w: int, h: int, radius: int,
) -> None:
    """이미지 없을 때 회색 플레이스홀더 직사각형을 그린다."""
    try:
        draw.rounded_rectangle([(x, y), (x + w, y + h)], radius=radius, fill="#CCCCCC")
    except AttributeError:
        draw.rectangle([(x, y), (x + w, y + h)], fill="#CCCCCC")
