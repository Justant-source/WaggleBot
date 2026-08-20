"""ai_worker/renderer/_frames.py — PIL 프레임 렌더링 함수 (internal)

와글 브랜드 디자인 v3 (기본 테마):
  - 옐로우 헤더 #FBD024 + 코드 드로잉 (base_layout.png 불필요)
  - 제목블록: 굵은 검정 제목 + 메타줄 + 구분선
  - 자막: 굵은 검정 #161616, 흐림 없음, 위로 누적
  - 미디어: 자연비율 contain (좌우 흰여백)
  - 아웃트로: 마스코트 + 참여 유도 질문 + 댓글입력 목업
  - 댓글씬: 아바타·닉네임·BEST·추천수 세로 리스트

다시봄 Tone L 테마 (site_code=='again_spring', layout['global']['theme']=='tone_l'):
  - 옐로우 헤더 제거 — 배경과 같은 톤(#EDF1E8) + 하단 보더(#D3DCC9)
  - 제목·본문 낭독(인트로 훅·이미지 캡션·text_only·비디오 자막) = 세리프(Noto Serif KR
    Medium) + 좌측 정렬(제목블록과 동일 여백). UI/메타(채널명·메타줄)는 산세리프 유지
  - 색상·정렬·폰트 분기는 `_theme_name()` / `_body_font_file()` / `_body_align()` 참조.
    댓글·아웃트로 세부 스타일(블러·페이드·진영색 등)은 이 테마 분기 대상이 아님(별도 작업).
"""

import datetime
import hashlib
import logging
import shutil
from pathlib import Path
from typing import Optional

import requests
from PIL import Image, ImageDraw, ImageFilter, ImageFont

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

# Tone L 카테고리 칩 한글 표시명 (다시봄 카테고리 enum → 표시 텍스트)
_CATEGORY_KO = {
    "COUPLE": "연인", "MARRIED": "부부", "FAMILY": "가족",
    "WORK": "직장", "FRIEND": "친구", "OTHER": "기타",
}


# ---------------------------------------------------------------------------
# 테마 헬퍼 — 사이트별 크로마·타이포 분기 (기본: 와글 / again_spring: Tone L)
#
# 색상은 config/layout.json의 `themes.tone_l`가 layout.py에서 site_code=='again_spring'
# 일 때만 병합되어 layout['global']/['scenes']에 이미 반영된 상태로 들어온다. 여기서는
# 색상 자체를 분기하지 않고, config만으로 표현할 수 없는 폰트 패밀리·정렬만 분기한다.
# ---------------------------------------------------------------------------

def _theme_name(layout: dict) -> str:
    """layout['global']['theme'] — 'tone_l'(다시봄) 또는 기본값('waggle')."""
    return layout.get("global", {}).get("theme", "waggle")


def _title_font_file(layout: dict) -> str:
    """제목블록(헤더 아래 제목) 폰트 — Tone L: 세리프 Medium(굵기 500), 기본: 산세리프 Bold."""
    return "NotoSerifKR-Medium.ttf" if _theme_name(layout) == "tone_l" else "NotoSansKR-Bold.ttf"


def _body_font_file(layout: dict) -> str:
    """본문 낭독 폰트 — 인트로 훅·이미지 캡션·text_only·비디오 자막 공통.

    Tone L: 감정이 실리는 자리는 세리프(디자인 SSOT 3.2절, 굵기 500 상한).
    기본(와글): 기존 산세리프 Bold 유지.
    """
    return "NotoSerifKR-Medium.ttf" if _theme_name(layout) == "tone_l" else "NotoSansKR-Bold.ttf"


def _channel_font_file(layout: dict) -> str:
    """헤더 채널명 폰트 — UI 요소라 Tone L에서도 산세리프 유지, 굵기만 Medium(500)으로 낮춘다."""
    return "NotoSansKR-Medium.ttf" if _theme_name(layout) == "tone_l" else "NotoSansKR-Bold.ttf"


def _body_align(layout: dict) -> tuple[str, int]:
    """본문 낭독 정렬 — Tone L: 제목블록과 동일 좌측 여백, 기본: 중앙."""
    if _theme_name(layout) == "tone_l":
        pad_x = layout.get("global", {}).get("title_block", {}).get("pad_x", 44)
        return "left", pad_x
    return "center", 0


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


def _composite_on_background(img: Image.Image, bg_color: str = "#FFFFFF") -> Image.Image:
    """알파 채널이 있는 이미지를 단색 배경 위에 합성해 RGB로 변환한다.

    투명 PNG(예: 메타포 일러스트)를 그냥 .convert("RGB")하면 투명 영역이
    검정으로 깔린다(알파 버림 시 밑에 깔린 RGB 값을 그대로 씀 — 대부분의
    SVG→PNG 변환기가 투명 영역 RGB를 (0,0,0)으로 채워두기 때문). 알파를
    실제 배경색 위에 합성한 뒤 RGB로 평탄화해야 의도한 배경색이 나온다.
    """
    if img.mode in ("RGBA", "LA") or ("transparency" in img.info):
        rgba = img.convert("RGBA")
        bg = Image.new("RGBA", rgba.size, bg_color)
        bg.alpha_composite(rgba)
        return bg.convert("RGB")
    return img.convert("RGB")


def _load_image(
    src: str, cache_dir: Path, max_retries: int = 2, bg_color: str = "#FFFFFF",
) -> Optional[Image.Image]:
    """URL 또는 로컬 경로에서 이미지 로드. 실패 시 재시도 후 None.

    bg_color: 알파 채널이 있는 이미지(투명 PNG)를 평탄화할 때 깔 배경색.
    다시봄 Tone L 메타포 이미지는 실제로 투명 PNG이므로, 호출측(layout.py)이
    테마 팔레트의 surface 색을 넘겨 검정 배경 버그를 방지한다.
    """
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
            return _composite_on_background(Image.open(cache_path), bg_color)
        except Exception as e:
            logger.warning("이미지 열기 실패: %s — %s", cache_path, e)
            return None
    try:
        return _composite_on_background(Image.open(src), bg_color)
    except Exception as e:
        logger.warning("로컬 이미지 로드 실패: %s — %s", src, e)
        return None



def _sanitize_comment_display_text(value: object) -> str:
    """댓글 표시용 텍스트를 정규화한다.

    수집 단계의 이스케이프가 남아 있어도 ``\\n``은 실제 줄바꿈으로 보이고,
    그 밖의 잔여 백슬래시는 화면에 노출하지 않는다.
    """
    text = str(value or "")
    text = text.replace("\\r\\n", "\n").replace("\\n", "\n")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text.replace("\\", "").strip()


def _draw_down_chevron(
    draw: ImageDraw.ImageDraw,
    center_x: int,
    center_y: int,
    size: int,
    color: str,
    width: int = 3,
) -> None:
    """폰트 글리프 대신 PIL 선으로 아래쪽 셰브론을 그린다."""
    half = max(2, size // 2)
    draw.line(
        [(center_x - half, center_y - half // 2),
         (center_x, center_y + half // 2),
         (center_x + half, center_y - half // 2)],
        fill=color,
        width=width,
    )



def _flatten_rgba(img: Image.Image, bg: str = "#FFF8F0") -> Image.Image:
    """RGBA(투명) → RGB. 투명 영역을 크림으로 채워 검정 배경 오염을 막는다."""
    if img.mode == "RGBA":
        base = Image.new("RGB", img.size, bg)
        base.paste(img, mask=img.split()[3])
        return base
    return img.convert("RGB") if img.mode != "RGB" else img

def _fit_cover(img: Image.Image, w: int, h: int) -> Image.Image:
    """Cover 모드: 비율 유지 + 중앙 크롭."""
    img = _flatten_rgba(img)
    iw, ih = img.size
    scale = max(w / iw, h / ih)
    nw, nh = int(iw * scale), int(ih * scale)
    img = img.resize((nw, nh), Image.LANCZOS)
    left = (nw - w) // 2
    top = (nh - h) // 2
    return img.crop((left, top, left + w, top + h))


def _fit_contain(img: Image.Image, max_w: int, max_h: int) -> Image.Image:
    """Contain 모드: 비율 유지, 최대 크기 이하로 리사이즈 (크롭 없음, 흰여백)."""
    img = _flatten_rgba(img)
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


# ---------------------------------------------------------------------------
# Tone L 헬퍼 함수들
# ---------------------------------------------------------------------------

def _draw_sprout_mark(draw, cx, cy, size, palette):
    """다시봄 식물 마크 — 두 잎 타원 + 줄기 + 씨앗."""
    leaf_w = int(size * 0.25)
    leaf_h = int(size * 0.45)
    lx_off = int(size * 0.15)
    ly_off_top = int(size * -0.12)
    draw.ellipse([(cx - lx_off - leaf_w // 2, cy + ly_off_top - leaf_h // 2),
                  (cx - lx_off + leaf_w // 2, cy + ly_off_top + leaf_h // 2)],
                 fill=palette.get("peach", "#C9785A"))
    rx_off = int(size * 0.15)
    ry_off_top = int(size * -0.12)
    draw.ellipse([(cx + rx_off - leaf_w // 2, cy + ry_off_top - leaf_h // 2),
                  (cx + rx_off + leaf_w // 2, cy + ry_off_top + leaf_h // 2)],
                 fill=palette.get("sage", "#5F8F76"))
    stem_x = cx
    stem_y_top = cy + int(size * 0.15)
    stem_y_bot = cy + int(size * 0.35)
    draw.rectangle([(stem_x - 1, stem_y_top), (stem_x + 1, stem_y_bot)],
                   fill=palette.get("muted", "#A08670"))
    seed_r = int(size * 0.04)
    seed_y = stem_y_bot + int(size * 0.06)
    draw.ellipse([(stem_x - seed_r, seed_y - seed_r), (stem_x + seed_r, seed_y + seed_r)],
                 fill=palette.get("ink", "#5C4030"))


def _draw_step_dots(draw, canvas_w, stage, layout):
    """3단계 스텝 닷 페이저."""
    cfg = layout.get("themes", {}).get("tone_l", {}).get("step_dots", {})
    dot_size = cfg.get("dot_size", 18)
    pill_w = cfg.get("pill_width", 52)
    pill_h = cfg.get("pill_height", 18)
    gap = cfg.get("gap_between", 24)
    inactive_c = cfg.get("dot_inactive_color", "#E5DED2")
    active_c = cfg.get("pill_active_color", "#C9785A")
    canvas_h = layout.get("canvas", {}).get("height", 1920)
    ribbon_h = layout.get("themes", {}).get("tone_l", {}).get("ribbon", {}).get("height", 22)
    dots_y = canvas_h - ribbon_h - cfg.get("gap_bottom", 80)
    total_w = pill_w + gap + dot_size + gap + dot_size
    dots_x = (canvas_w - total_w) // 2
    for i, dot_stage in enumerate([1, 2, 3]):
        if i == 0:
            pos_x = dots_x
        elif i == 1:
            pos_x = dots_x + pill_w + gap
        else:
            pos_x = dots_x + pill_w + gap + dot_size + gap
        if stage == dot_stage:
            pill_y = dots_y + (dot_size - pill_h) // 2
            try:
                draw.rounded_rectangle([(pos_x, pill_y), (pos_x + pill_w, pill_y + pill_h)],
                                      radius=pill_h // 2, fill=active_c)
            except TypeError:
                draw.rectangle([(pos_x, pill_y), (pos_x + pill_w, pill_y + pill_h)], fill=active_c)
        else:
            draw.ellipse([(pos_x, dots_y), (pos_x + dot_size, dots_y + dot_size)], fill=inactive_c)


def _draw_ribbon(draw, canvas_w, canvas_h, layout):
    """하단 리본 — 좌 peach, 우 sage."""
    cfg = layout.get("themes", {}).get("tone_l", {}).get("ribbon", {})
    ribbon_h = cfg.get("height", 22)
    left_c = cfg.get("left_color", "#C9785A")
    right_c = cfg.get("right_color", "#5F8F76")
    mid_x = canvas_w // 2
    ribbon_y = canvas_h - ribbon_h
    draw.rectangle([(0, ribbon_y), (mid_x, canvas_h)], fill=left_c)
    draw.rectangle([(mid_x, ribbon_y), (canvas_w, canvas_h)], fill=right_c)


def _draw_chip(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    text: str,
    font: ImageFont.FreeTypeFont,
    active: bool,
    palette: dict,
) -> int:
    """pill 배지(카테고리/정렬 칩 공용). 다음 칩을 이어그릴 x좌표를 반환한다."""
    pad_x, pad_y = 18, 10
    tw = int(_font_w(font, text))
    try:
        ascent, descent = font.getmetrics()
        th = ascent + descent
    except Exception:
        th = int(getattr(font, "size", 26) * 1.3)
    w = tw + pad_x * 2
    h = th + pad_y * 2
    if active:
        fill = palette.get("sage", "#5F8F76")
        text_color = palette.get("surface", "#FFF8F0")
        outline = None
    else:
        fill = palette.get("card", "#FFFFFF")
        text_color = palette.get("muted", "#A08670")
        outline = palette.get("border", "#E5DED2")
    try:
        if outline:
            draw.rounded_rectangle([(x, y), (x + w, y + h)], radius=h // 2,
                                   fill=fill, outline=outline, width=2)
        else:
            draw.rounded_rectangle([(x, y), (x + w, y + h)], radius=h // 2, fill=fill)
    except AttributeError:
        draw.rectangle([(x, y), (x + w, y + h)], fill=fill)
    draw.text((x + pad_x, y + pad_y), text, font=font, fill=text_color)
    return x + w


def _draw_card(
    img: Image.Image,
    x: int,
    y: int,
    w: int,
    h: int,
    radius: int,
    palette: dict,
    border_color: str | None = None,
) -> Image.Image:
    """흰 카드(배경+보더+옅은 그림자)를 img 위에 합성해 반환한다."""
    if img.mode != "RGBA":
        img = img.convert("RGBA")

    shadow_pad = 30
    shadow = Image.new("RGBA", (w + shadow_pad * 2, h + shadow_pad * 2), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    try:
        sd.rounded_rectangle(
            [(shadow_pad, shadow_pad + 6), (shadow_pad + w, shadow_pad + h + 6)],
            radius=radius, fill=(60, 45, 25, 60),
        )
    except AttributeError:
        sd.rectangle(
            [(shadow_pad, shadow_pad + 6), (shadow_pad + w, shadow_pad + h + 6)],
            fill=(60, 45, 25, 60),
        )
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=14))
    img.alpha_composite(shadow, (x - shadow_pad, y - shadow_pad))

    draw = ImageDraw.Draw(img)
    card_bg = palette.get("card", "#FFFFFF")
    card_border = border_color or palette.get("border", "#E5DED2")
    try:
        draw.rounded_rectangle([(x, y), (x + w, y + h)], radius=radius,
                               fill=card_bg, outline=card_border, width=2)
    except TypeError:
        draw.rounded_rectangle([(x, y), (x + w, y + h)], radius=radius, fill=card_bg)
    return img


def _truncate(text: str, max_chars: int) -> str:
    """max_chars 초과 시 (max_chars-2)자 + '..'."""
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 2] + ".."


# getbbox로 잉크 폭을 맞추고, 측정 오차만 소량 보정한다.
# (예전 4% slack + 16px는 한 줄이 너무 짧아지는 부작용이 있었음)
_WRAP_WIDTH_SLACK = 1.01
_WRAP_SAFETY_PX = 4


def _font_w(font: ImageFont.FreeTypeFont, text: str) -> float:
    """폰트 기준 텍스트 픽셀 너비 (그리기 폭에 가깝게, 소량 여유 포함)."""
    if not text:
        return 0.0
    try:
        bbox = font.getbbox(text)
        w = float(bbox[2] - bbox[0])
    except Exception:
        try:
            w = float(font.getlength(text))
        except AttributeError:
            w = float(font.getsize(text)[0])  # type: ignore[attr-defined]
    return w * _WRAP_WIDTH_SLACK


def _wrap_max_width(raw: int) -> int:
    """줄바꿈 한도 — 카드/씬 pad가 오른쪽 여백; 여기선 측정 오차만 뺀다."""
    return max(1, int(raw) - _WRAP_SAFETY_PX)


def _wrap_korean(
    text: str,
    font: ImageFont.FreeTypeFont,
    max_width: int,
    keep_all: bool = False,
) -> list[str]:
    """한글 텍스트 줄바꿈 — 단어(공백) 단위 우선.

    keep_all=True: 단어 내 강제분리 없음 (어절 단위 유지, 제목·댓글용).
    keep_all=False: 긴 단어는 글자 단위 강제 분리 (기본값).

    하드 줄바꿈(`\n`)은 먼저 분리한다. 남겨 두면 PIL ImageDraw.text가 한
    호출 안에서 여러 줄을 그려, 호출측 line_height 루프와 겹친다.
    """
    if not text:
        return [""]
    paragraphs = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    out: list[str] = []
    safe_w = _wrap_max_width(max_width)
    for para in paragraphs:
        out.extend(_wrap_korean_paragraph(para, font, safe_w, keep_all=keep_all))
    return out or [""]


def _wrap_korean_paragraph(
    text: str,
    font: ImageFont.FreeTypeFont,
    max_width: int,
    *,
    keep_all: bool = False,
) -> list[str]:
    """개행이 없는 단일 단락을 폭 기준으로 줄바꿈한다."""
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
    align: str = "center",
    pad_x: int = 0,
) -> int:
    """줄 목록을 정렬(align)로 그리고, 마지막 줄 아래 y를 반환한다.

    align="center" (기본, 하위호환): 캔버스 중앙 정렬.
    align="left": pad_x 여백에서 좌측 정렬 (Tone L 본문 낭독용).
    """
    y = y_start
    for line in lines:
        if align == "left":
            cx = pad_x
        else:
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


def _relative_time(dt: datetime.datetime | str | None) -> str:
    """datetime(또는 ISO 문자열) → '3시간 전' 형식 상대 시간 문자열. None/파싱 실패면 ''.

    comment_items["created_at"]는 SceneDirector가 ``datetime.isoformat()`` 문자열로
    직렬화해 전달한다 — 문자열/datetime 양쪽을 모두 허용한다.
    """
    if dt is None or dt == "":
        return ""
    if isinstance(dt, str):
        try:
            dt = datetime.datetime.fromisoformat(dt)
        except ValueError:
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
    """브랜드 헤더바 + 셰브론(‹) + 채널명 + 햄버거(≡)를 그린다.

    기본(와글): 옐로우 배경. Tone L(다시봄): 배경과 같은 톤 + 하단 보더(옐로우 바 없음).
    """
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
    theme = _theme_name(layout)

    # 배경
    draw.rectangle([(0, 0), (cw, h)], fill=bg)

    # Tone L: 색 블록 대신 하단 얇은 보더로만 헤더 영역을 구분 (옐로우 바 없음)
    if theme == "tone_l":
        border_color = hdr.get("border_color", "#D3DCC9")
        border_th = hdr.get("border_thickness", 2)
        draw.rectangle([(0, h - border_th), (cw, h)], fill=border_color)

    cy = h // 2
    safe_x = 90 if theme == "tone_l" else 52

    # 셰브론 (‹) — 좌측 아이콘
    arm = 28
    tip_x = safe_x
    draw.line(
        [(tip_x + arm, cy - arm), (tip_x, cy), (tip_x + arm, cy + arm)],
        fill=ink, width=stroke,
    )

    # 채널명 — 수평 중앙 (Tone L: 새싹 마크 + 텍스트를 한 블록으로 중앙 정렬)
    font = _load_font(font_dir, _channel_font_file(layout), title_fs)
    tw = int(_font_w(font, channel))
    if theme == "tone_l":
        palette = g.get("palette", {})
        mark_size = 58
        mark_gap = 16
        block_w = mark_size + mark_gap + tw
        block_x = (cw - block_w) // 2
        mark_cx = block_x + mark_size // 2
        _draw_sprout_mark(draw, mark_cx, cy, mark_size, palette)
        tx = block_x + mark_size + mark_gap
        ty = (h - title_fs) // 2 - 2
        draw.text((tx, ty), channel, font=font, fill=ink)
    else:
        tx = (cw - tw) // 2
        ty = (h - title_fs) // 2 - 2
        draw.text((tx, ty), channel, font=font, fill=ink)

    # 햄버거 (≡) — 우측
    mx = cw - safe_x - 52
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
    font = _load_font(font_dir, _title_font_file(layout), font_size)
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
    Tone L: intro 전용 상단블록(칩+큰제목+메타) 기준으로 계산한다.
    """
    from ai_worker.renderer.layout import _load_font

    if _theme_name(layout) == "tone_l":
        return _draw_intro_topblock(None, layout, title, font_dir, None)

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
    font = _load_font(font_dir, _title_font_file(layout), font_size)
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

def _draw_intro_topblock(
    draw: ImageDraw.ImageDraw,
    layout: dict,
    title: str,
    font_dir: Path,
    meta: dict | None,
) -> int:
    """Tone L intro 전용 상단 블록 — 칩(카테고리+정렬) + 큰 제목 + 메타줄.

    드로잉과 계산(pure) 양쪽에서 재사용하도록 draw=None이면 계산만 하고 그리지 않는다.
    """
    from ai_worker.renderer.layout import _load_font

    g = layout["global"]
    hdr_h = g["header"].get("height", 240)
    pad_x = g.get("title_block", {}).get("pad_x", 90)
    max_lines = g.get("title_block", {}).get("max_lines", 3)
    palette = g.get("palette", {})
    cw = layout["canvas"]["width"]

    sc = layout["scenes"]["intro"]
    chips_cfg = sc.get("chips", {})
    title_cfg = sc.get("title", {})
    meta_cfg = sc.get("meta", {})

    chip_fs = chips_cfg.get("font_size", 26)
    chip_font = _load_font(font_dir, "NotoSansKR-Medium.ttf", chip_fs)
    chips_y = hdr_h + chips_cfg.get("gap_top", 8)
    chips_h = int(chip_fs * 1.3) + 20

    meta_dict = meta or {}
    category = meta_dict.get("category")
    cat_label = _CATEGORY_KO.get(category, category) if category else None

    if draw is not None:
        cx = pad_x
        if cat_label:
            cx = _draw_chip(draw, cx, chips_y, cat_label, chip_font, True, palette) + chips_cfg.get("gap_between", 12)
        _draw_chip(draw, cx, chips_y, "최신순", chip_font, False, palette)

    chips_bottom = chips_y + chips_h

    title_fs = title_cfg.get("font_size", 62)
    title_lh = title_cfg.get("line_height", 76)
    title_font = _load_font(font_dir, _title_font_file(layout), title_fs)
    max_w = cw - 2 * pad_x
    wrapped = _wrap_korean(title, title_font, max_w, keep_all=True)
    n_lines = min(len(wrapped), max_lines)
    ty = chips_bottom + title_cfg.get("gap_top", 36)
    if draw is not None:
        for line in wrapped[:n_lines]:
            draw.text((pad_x, ty), line, font=title_font, fill=palette.get("ink", "#5C4030"))
            ty += title_lh
    else:
        ty += n_lines * title_lh
    title_bottom = ty

    meta_fs = meta_cfg.get("font_size", 28)
    meta_gap = meta_cfg.get("gap_top", 22)
    my = title_bottom + meta_gap
    if draw is not None:
        meta_font = _load_font(font_dir, "NotoSansKR-Medium.ttf", meta_fs)
        parts = []
        author = (meta_dict.get("author") or "").strip() or "익명"
        parts.append(author)
        t = (meta_dict.get("time") or "").strip()
        if t:
            parts.append(t)
        v = (meta_dict.get("views") or "").strip()
        if v and v != "0":
            parts.append(f"조회 {v}")
        meta_text = " · ".join(parts)
        draw.text((pad_x, my), meta_text, font=meta_font, fill=meta_cfg.get("color", "#A08670"))

    return int(my + int(meta_fs * 1.35))


def _create_base_frame(
    layout: dict,
    title: str,
    font_dir: Path,
    assets_dir: Path,
    meta: dict | None = None,
) -> Image.Image:
    """베이스 프레임: 흰 캔버스 + 헤더바 + 상단 블록.

    와글: 옐로우 헤더바 + 제목블록(제목+메타+구분선).
    Tone L: 헤더바(새싹마크) + intro 전용 상단블록(칩+큰제목+메타) — intro 씬 전용.
    assets_dir는 하위 호환용 파라미터(현재 미사용).
    """
    g = layout["global"]
    cw = layout["canvas"]["width"]
    ch = layout["canvas"]["height"]
    theme = _theme_name(layout)

    base = Image.new("RGB", (cw, ch), g.get("background_color", "#FFFFFF"))
    draw = ImageDraw.Draw(base)

    _draw_header(draw, layout, font_dir)
    if theme == "tone_l":
        _draw_intro_topblock(draw, layout, title, font_dir, meta)
    else:
        _draw_title_block(draw, layout, title, font_dir, meta=meta)

    return base


def _create_breadcrumb_frame(
    layout: dict,
    title: str,
    font_dir: Path,
    meta: dict | None = None,
    show_title: bool = True,
) -> Image.Image:
    """Tone L 전용: 헤더 + 브레드크럼(카테고리 칩 + 익명·시간) [+ 작은 제목 1줄].

    body(image_text/text_only)/comments 씬이 사용 — intro의 큰 제목블록과 달리
    가볍게 상단만 표시한다. 와글(비-tone_l) 사이트에서는 호출되지 않지만,
    안전하게 _create_base_frame과 동일하게 동작한다.
    """
    from ai_worker.renderer.layout import _load_font

    g = layout["global"]
    cw = layout["canvas"]["width"]
    ch = layout["canvas"]["height"]
    theme = _theme_name(layout)

    base = Image.new("RGB", (cw, ch), g.get("background_color", "#FFFFFF"))
    draw = ImageDraw.Draw(base)
    _draw_header(draw, layout, font_dir)

    if theme != "tone_l":
        _draw_title_block(draw, layout, title, font_dir, meta=meta)
        return base

    hdr_h = g["header"].get("height", 240)
    pad_x = g.get("title_block", {}).get("pad_x", 90)
    palette = g.get("palette", {})
    # image_text의 breadcrumb 설정을 공용으로 사용 (image_text/text_only/comments 동일 스타일)
    bc_cfg = layout["scenes"].get("image_text", {}).get("breadcrumb", {})
    title_cfg = layout["scenes"].get("image_text", {}).get("title", {})

    bc_fs = bc_cfg.get("font_size", 26)
    chip_font = _load_font(font_dir, "NotoSansKR-Medium.ttf", bc_fs)
    y = hdr_h + bc_cfg.get("gap_top", 8)

    meta_dict = meta or {}
    category = meta_dict.get("category")
    cat_label = _CATEGORY_KO.get(category, category) if category else None
    cx = pad_x
    if cat_label:
        cx = _draw_chip(draw, cx, y, cat_label, chip_font, True, palette) + 12

    meta_font = _load_font(font_dir, "NotoSansKR-Medium.ttf", bc_fs)
    parts = []
    t = (meta_dict.get("time") or "").strip()
    parts.append("익명" if not (meta_dict.get("author") or "").strip() else meta_dict["author"].strip())
    if t:
        parts.append(t)
    meta_text = " · ".join(parts)
    ty_meta = y + 8
    draw.text((cx + 14, ty_meta), meta_text, font=meta_font, fill=palette.get("muted", "#A08670"))

    bc_bottom = y + int(bc_fs * 1.3) + 20

    if show_title:
        t_fs = title_cfg.get("font_size", 38)
        t_font = _load_font(font_dir, "NotoSansKR-Bold.ttf", t_fs)
        max_w = cw - 2 * pad_x
        line = _truncate(title, 26)
        ty = bc_bottom + title_cfg.get("gap_top", 20)
        draw.text((pad_x, ty), line, font=t_font, fill=title_cfg.get("color", "#A08670"))

    return base


def _breadcrumb_bottom_y(
    layout: dict,
    title: str,
    font_dir: Path,
    show_title: bool = True,
) -> int:
    """_create_breadcrumb_frame과 동일 계산을 드로잉 없이 수행 — 콘텐츠 시작 Y 반환."""
    if _theme_name(layout) != "tone_l":
        return _title_block_bottom_y(layout, title, font_dir)

    g = layout["global"]
    hdr_h = g["header"].get("height", 240)
    bc_cfg = layout["scenes"].get("image_text", {}).get("breadcrumb", {})
    title_cfg = layout["scenes"].get("image_text", {}).get("title", {})
    bc_fs = bc_cfg.get("font_size", 26)

    y = hdr_h + bc_cfg.get("gap_top", 8)
    bc_bottom = y + int(bc_fs * 1.3) + 20

    if not show_title:
        return int(bc_bottom) + 8

    t_fs = title_cfg.get("font_size", 38)
    t_gap = title_cfg.get("gap_top", 20)
    t_lh = int(t_fs * 1.4)
    return int(bc_bottom + t_gap + t_lh)


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
    stage: int | None = None,
) -> Path:
    """씬 intro — hook 자막(중앙, 굵은 검정) + 자연비율 표지 이미지.

    Tone L: 자막 없음(상단 블록이 이미 제목을 표시) — 메타포 이미지가 아래 남은
    영역을 COVER로 꽉 채운다(스텝닷 위까지). 기본(와글): 기존 자막+contain 유지.
    """
    from ai_worker.renderer.layout import _load_font

    theme = _theme_name(layout)
    sc = layout["scenes"]["intro"]
    cw = layout["canvas"]["width"]
    ch = layout["canvas"]["height"]

    img = base_frame.copy()
    draw = ImageDraw.Draw(img)

    if theme == "tone_l":
        media_cfg = sc.get("media", {})
        pad_x = layout["global"].get("title_block", {}).get("pad_x", 90)
        media_radius = media_cfg.get("radius", 16)
        media_gap = media_cfg.get("gap_top", 48)
        step_cfg = layout.get("themes", {}).get("tone_l", {}).get("step_dots", {})
        ribbon_h = layout.get("themes", {}).get("tone_l", {}).get("ribbon", {}).get("height", 22)
        dots_reserve = step_cfg.get("gap_bottom", 80) + step_cfg.get("dot_size", 18) + 20

        media_y = content_top + media_gap
        media_bottom = ch - ribbon_h - dots_reserve
        media_h = max(100, media_bottom - media_y)
        media_w = cw - 2 * pad_x
        if img_pil is not None:
            fitted = _fit_cover(img_pil, media_w, media_h)
            img = _paste_rounded(img, fitted, pad_x, media_y, media_radius)

        img = img.convert("RGB")
        draw = ImageDraw.Draw(img)
        _draw_step_dots(draw, cw, stage or 1, layout)
        _draw_ribbon(draw, cw, ch, layout)
        img.save(str(out_path), "PNG")
        return out_path

    sc_cap = sc
    cap_cfg = sc_cap.get("caption", {})
    media_cfg = sc_cap.get("media", {})

    cap_fs: int = cap_cfg.get("font_size", 50)
    cap_lh: int = cap_cfg.get("line_height", 62)
    cap_color: str = cap_cfg.get("color", "#161616")
    cap_pad_top: int = cap_cfg.get("pad_top", 56)
    cap_max_w: int = cap_cfg.get("max_width", 900)
    cap_max_lines: int = cap_cfg.get("max_lines", 2)

    media_max_w: int = media_cfg.get("max_width", 820)
    media_gap: int = media_cfg.get("gap_top", 56)
    media_radius: int = media_cfg.get("radius", 8)

    font = _load_font(font_dir, _body_font_file(layout), cap_fs)
    align, cap_pad_x = _body_align(layout)

    # 자막 (위)
    cap_y = content_top + cap_pad_top
    cap_bottom = cap_y
    if hook_text:
        lines = _wrap_korean(hook_text, font, cap_max_w)[:cap_max_lines]
        _draw_centered_text(draw, lines, font, cap_y, cap_lh, cap_color, cw,
                            align=align, pad_x=cap_pad_x)
        cap_bottom = cap_y + len(lines) * cap_lh

    # 미디어 (자연비율 contain, 중앙 배치). 이미지 없으면 크림 빈화면만 (회색 박스 금지).
    media_y = cap_bottom + media_gap
    if img_pil is not None:
        max_h = max(100, ch - media_y - 60)
        fitted = _fit_contain(img_pil, media_max_w, max_h)
        nw, nh = fitted.size
        mx = (cw - nw) // 2
        img = _paste_rounded(img, fitted, mx, media_y, media_radius)

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
    stage: int | None = None,
    display_lines: list[str] | None = None,
) -> Path:
    """씬 image_text — 자막(위) + 자연비율 이미지(좌우 흰여백).

    Tone L: 브레드크럼은 이미 base_frame(breadcrumb_frame)에 그려진 상태로 들어온다.
    카드 안에 인용구 텍스트 + 1:1 이미지를 배치한다.
    """
    from ai_worker.renderer.layout import _load_font

    theme = _theme_name(layout)
    sc = layout["scenes"]["image_text"]
    cw = layout["canvas"]["width"]
    ch = layout["canvas"]["height"]

    if theme == "tone_l":
        palette = layout["global"].get("palette", {})
        pad_x = layout["global"].get("title_block", {}).get("pad_x", 90)
        card_cfg = sc.get("card", {})
        quote_cfg = sc.get("quote", {})
        image_cfg = sc.get("image", {})

        card_x = pad_x
        card_w = cw - 2 * pad_x
        card_pad = card_cfg.get("pad", 44)
        card_radius = card_cfg.get("radius", 28)
        card_y = content_top + card_cfg.get("gap_top", 36)

        q_fs = quote_cfg.get("font_size", 54)
        q_lh = quote_cfg.get("line_height", 68)
        q_font = _load_font(font_dir, _body_font_file(layout), q_fs)
        inner_w = card_w - 2 * card_pad
        # max_lines: 문장 1회 등장당 시각 줄 수 상한(길면 wrap). 등장 횟수 제한이 아님.
        q_max_lines = int(quote_cfg.get("max_lines", 8))
        if display_lines:
            q_lines = [line for line in display_lines if line.strip()][: min(q_max_lines, 3)]
        else:
            q_lines = _wrap_korean(text, q_font, inner_w, keep_all=True)[:q_max_lines]

        img_size = card_w - 2 * card_pad
        img_gap = image_cfg.get("gap_top", 40)
        card_h = card_pad + len(q_lines) * q_lh + img_gap + img_size + card_pad
        max_card_h = ch - card_y - 140
        if card_h > max_card_h:
            card_h = max_card_h
            img_size = max(200, card_h - card_pad - len(q_lines) * q_lh - img_gap - card_pad)

        img = base_frame.copy()
        img = _draw_card(img, card_x, card_y, card_w, card_h, card_radius, palette)
        draw = ImageDraw.Draw(img)

        ty = card_y + card_pad
        for line in q_lines:
            draw.text((card_x + card_pad, ty), line, font=q_font,
                      fill=quote_cfg.get("color", "#5C4030"))
            ty += q_lh

        if img_pil is not None:
            img_radius = image_cfg.get("radius", 20)
            fitted = _fit_cover(img_pil, img_size, img_size)
            img = _paste_rounded(img.convert("RGB"), fitted, card_x + card_pad, ty + img_gap, img_radius)

        img = img.convert("RGB")
        draw = ImageDraw.Draw(img)
        _draw_step_dots(draw, cw, stage or 2, layout)
        _draw_ribbon(draw, cw, ch, layout)
        img.save(str(out_path), "PNG")
        return out_path

    cap_cfg = sc.get("caption_above", {})
    media_cfg = sc.get("media", {})

    cap_fs: int = cap_cfg.get("font_size", 50)
    cap_lh: int = cap_cfg.get("line_height", 62)
    cap_color: str = cap_cfg.get("color", "#161616")
    cap_pad_top: int = cap_cfg.get("pad_top", 56)
    cap_max_w: int = cap_cfg.get("max_width", 900)
    cap_max_lines: int = cap_cfg.get("max_lines", 2)

    media_max_w: int = media_cfg.get("max_width", 820)
    media_gap: int = media_cfg.get("gap_top", 48)
    media_radius: int = media_cfg.get("radius", 8)

    font = _load_font(font_dir, _body_font_file(layout), cap_fs)
    align, cap_pad_x = _body_align(layout)
    img = base_frame.copy()
    draw = ImageDraw.Draw(img)

    # 자막 (위)
    cap_y = content_top + cap_pad_top
    lines = _wrap_korean(text, font, cap_max_w)[:cap_max_lines]
    if lines:
        _draw_centered_text(draw, lines, font, cap_y, cap_lh, cap_color, cw,
                            align=align, pad_x=cap_pad_x)
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
    stage: int | None = None,
) -> Path:
    """씬 text_only — 자막 누적 표시.

    Tone L: 불릿 스타일 — 과거 문장(muted+border 불릿) vs 현재 문장(ink+peach 불릿).
    기본(와글): 기존 굵은 검정 누적 표시 유지.
    """
    from ai_worker.renderer.layout import _load_font

    theme = _theme_name(layout)
    cw = layout["canvas"]["width"]
    ch = layout["canvas"]["height"]
    img = base_frame.copy()
    draw = ImageDraw.Draw(img)

    if theme == "tone_l":
        palette = layout["global"].get("palette", {})
        pad_x = layout["global"].get("title_block", {}).get("pad_x", 90)
        sc = layout["scenes"]["text_only"]
        bul_cfg = sc.get("bullets", {})

        font_size = bul_cfg.get("font_size", 52)
        lh = bul_cfg.get("line_height", 84)
        font = _load_font(font_dir, _body_font_file(layout), font_size)

        y = content_top + bul_cfg.get("gap_top", 64)
        slot_gap = int(bul_cfg.get("slot_gap", 28))
        last_idx = len(text_history) - 1
        for entry_i, entry in enumerate(text_history):
            # 등장(문장 추가) 단위로 색 구분 — 한 등장이 길면 여러 시각 줄로 wrap
            is_current = entry_i == last_idx
            text_color = palette.get("ink", "#5C4030") if is_current else palette.get("muted", "#A08670")
            lines = entry.get("lines", [])
            for line_text in lines:
                draw.text((pad_x, y), line_text, font=font, fill=text_color)
                y += lh
            if entry_i < last_idx:
                y += slot_gap

        _draw_step_dots(draw, cw, stage or 2, layout)
        _draw_ribbon(draw, cw, ch, layout)
        img.save(str(out_path), "PNG")
        return out_path

    sc = layout["scenes"]["text_only"]
    ta = sc["elements"]["text_area"]

    font_size: int = ta.get("font_size", 50)
    lh: int = ta.get("line_height", 71)
    slot_gap: int = ta.get("slot_gap", 45)
    color: str = ta.get("color", "#161616")
    pad_top: int = ta.get("pad_top", 96)

    font = _load_font(font_dir, _body_font_file(layout), font_size)
    align, pad_x = _body_align(layout)

    y = content_top + pad_top
    for entry_i, entry in enumerate(text_history):
        if entry_i > 0:
            y += slot_gap  # 슬롯 간 간격 (첫 슬롯 제외)
        for line_text in entry.get("lines", []):
            if align == "left":
                cx = pad_x
            else:
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
    """씬 outro — 참여유도 질문 + 댓글입력 목업 (구독유도 없음).

    header_only_frame을 베이스로 사용 (제목블록 없음). 배경은 이미 site theme
    (와글: 흰색 / Again Spring Tone L: #EDF1E8)이 반영된 상태로 들어온다.

    기본(와글): 마스코트(코드 드로잉) + Bold 산세리프 질문(2줄 허용) + 서브캡션 + CTA.
    Tone L(``scenes.outro.mascot.enabled == false``): 마스코트 제거, 세리프 한 줄
    질문만으로 CTA를 구성 — 서브캡션·CTA 문구는 기본 비활성(``enabled: false``)으로
    "구독 유도" 류 부가 문구 없이 질문 하나에 집중한다.
    """
    from ai_worker.renderer.layout import _load_font

    theme = _theme_name(layout)
    sc = layout["scenes"]["outro"]
    g = layout["global"]
    hdr = g["header"]
    cw = layout["canvas"]["width"]
    ch = layout["canvas"]["height"]
    hdr_h: int = hdr.get("height", 150)

    img = header_only_frame.copy()
    draw = ImageDraw.Draw(img)

    if theme == "tone_l":
        palette = g.get("palette", {})
        sprout_cfg = sc.get("sprout_mark", {})
        q_cfg = sc.get("question", {})
        cta_cfg = sc.get("cta", {})
        pill_cfg = sc.get("input_pill", {})
        domain_cfg = sc.get("domain", {})

        mark_size = sprout_cfg.get("size", 200)
        y = hdr_h + sprout_cfg.get("gap_top", 48)
        _draw_sprout_mark(draw, cw // 2, y + mark_size // 2, mark_size, palette)
        y += mark_size

        q_fs = q_cfg.get("font_size", 72)
        q_lh = q_cfg.get("line_height", 90)
        q_font = _load_font(font_dir, "NotoSansKR-Bold.ttf", q_fs)
        question = overlay_text.strip() or "여러분이라면 어떻게 하셨을까요?"
        q_lines = _wrap_korean(question, q_font, q_cfg.get("max_width", 900))
        q_y = y + q_cfg.get("gap_top", 48)
        _draw_centered_text(draw, q_lines, q_font, q_y, q_lh, q_cfg.get("color", "#5C4030"), cw)
        y = q_y + len(q_lines) * q_lh

        # CTA 문구("댓글로 여러분의 생각을 남겨주세요" 등) — enabled=false면 완전 생략
        if cta_cfg.get("enabled", False):
            cta_fs = cta_cfg.get("font_size", 48)
            cta_font = _load_font(font_dir, "NotoSansKR-Bold.ttf", cta_fs)
            cta_text = cta_cfg.get("text", "").strip()
            if cta_text:
                cta_lines = _wrap_korean(cta_text, cta_font, 900)
                cta_y = y + cta_cfg.get("gap_top", 40)
                _draw_centered_text(draw, cta_lines, cta_font, cta_y, int(cta_fs * 1.4),
                                    cta_cfg.get("color", "#5C4030"), cw)
                y = cta_y + len(cta_lines) * int(cta_fs * 1.4)

        box_w = pill_cfg.get("width", 860)
        box_h = pill_cfg.get("height", 104)
        box_x = (cw - box_w) // 2
        box_y = y + pill_cfg.get("gap_top", 72)
        box_r = pill_cfg.get("radius", box_h // 2)
        try:
            draw.rounded_rectangle([(box_x, box_y), (box_x + box_w, box_y + box_h)],
                                   radius=box_r, fill=pill_cfg.get("bg", "#FFFFFF"),
                                   outline=pill_cfg.get("border", "#E5DED2"),
                                   width=pill_cfg.get("border_width", 2))
        except TypeError:
            draw.rounded_rectangle([(box_x, box_y), (box_x + box_w, box_y + box_h)],
                                   radius=box_r, fill=pill_cfg.get("bg", "#FFFFFF"))
        av_size = pill_cfg.get("avatar_size", 68)
        av_margin = (box_h - av_size) // 2
        av_x0 = box_x + av_margin + 8
        av_y0 = box_y + av_margin
        draw.ellipse([(av_x0, av_y0), (av_x0 + av_size, av_y0 + av_size)],
                     fill=pill_cfg.get("avatar_bg", "#5F8F76"))
        av_font = _load_font(font_dir, "NotoSansKR-Bold.ttf", int(av_size * 0.42))
        draw.text((av_x0 + (av_size - int(_font_w(av_font, "나"))) // 2, av_y0 + int(av_size * 0.24)),
                  "나", font=av_font, fill=pill_cfg.get("avatar_label_color", "#FFF8F0"))
        ph_font = _load_font(font_dir, "NotoSansKR-Regular.ttf", int(box_h * 0.3))
        draw.text((av_x0 + av_size + 20, box_y + (box_h - int(box_h * 0.3)) // 2 - 2),
                  pill_cfg.get("placeholder", "댓글 추가..."), font=ph_font,
                  fill=pill_cfg.get("placeholder_color", "#C4B3A0"))
        arr_r = int(box_h * 0.2)
        arr_cx = box_x + box_w - av_margin - arr_r - 8
        arr_cy = box_y + box_h // 2
        draw.polygon([(arr_cx - arr_r, arr_cy - arr_r), (arr_cx - arr_r, arr_cy + arr_r),
                     (arr_cx + arr_r, arr_cy)], fill=pill_cfg.get("send_color", "#C9785A"))
        y = box_y + box_h

        dom_fs = domain_cfg.get("font_size", 34)
        dom_font = _load_font(font_dir, "NotoSansKR-Bold.ttf", dom_fs)
        dom_text = "againspring.net"
        dom_x = (cw - int(_font_w(dom_font, dom_text))) // 2
        dom_y = y + domain_cfg.get("gap_top", 56)
        draw.text((dom_x, dom_y), dom_text, font=dom_font, fill=domain_cfg.get("color", "#A08670"))

        _draw_ribbon(draw, cw, ch, layout)
        img.save(str(out_path), "PNG")
        return out_path

    mascot_cfg = sc.get("mascot", {})
    q_cfg = sc.get("question", {})
    sub_cfg = sc.get("sub_caption", {})
    box_cfg = sc.get("input_box", {})
    cta_cfg = sc.get("cta_text", {})
    hdr_bg: str = hdr.get("bg_color", "#FBD024")
    hdr_ink: str = hdr.get("ink_color", "#1A1A1A")

    mascot_enabled: bool = mascot_cfg.get("enabled", True)
    mascot_d: int = mascot_cfg.get("diameter", 220)
    mascot_pad: int = mascot_cfg.get("pad_top", 180)

    if mascot_enabled:
        # ── 마스코트 (코드 드로잉) ────────────────────────────────────────
        mascot_color: str = mascot_cfg.get("circle_color", "#1A1A1A")
        feature_color: str = mascot_cfg.get("feature_color", "#FBD024")

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
    else:
        # Tone L: 마스코트 없이 넉넉한 여백만 (편지지 호흡)
        y = hdr_h + int(sc.get("content_pad_top_no_mascot", mascot_pad + mascot_d))

    # ── 큰 질문 자막 ──────────────────────────────────────────────────────
    q_fs: int = q_cfg.get("font_size", 62)
    q_color: str = q_cfg.get("color", "#161616")
    q_gap: int = q_cfg.get("gap_top", 60)
    q_max_w: int = q_cfg.get("max_width", 900)
    q_lh: int = q_cfg.get("line_height", 78)
    q_font_file: str = q_cfg.get("font_family", "NotoSansKR-Bold.ttf")
    q_single_line: bool = bool(q_cfg.get("single_line", False))

    question = overlay_text.strip() or "여러분이라면 어떻게 하셨을까요?"
    q_font = _load_font(font_dir, q_font_file, q_fs)

    if q_single_line:
        # 한 줄 강제 — 폭 초과 시 폰트 크기를 점진적으로 줄여 한 줄에 맞춘다.
        cur_fs = q_fs
        while _font_w(q_font, question) > q_max_w and cur_fs > 32:
            cur_fs -= 2
            q_font = _load_font(font_dir, q_font_file, cur_fs)
        q_lines = [question]
    else:
        q_lines = _wrap_korean(question, q_font, q_max_w)

    q_y = y + q_gap
    _draw_centered_text(draw, q_lines, q_font, q_y, q_lh, q_color, cw)
    y = q_y + len(q_lines) * q_lh

    # ── 서브 캡션 (옵션 — Tone L 기본 비활성) ────────────────────────────
    if sub_cfg.get("enabled", True):
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
    av_bg: str = box_cfg.get("avatar_bg", hdr_bg)
    av_fg: str = box_cfg.get("avatar_fg", hdr_ink)
    send_color: str = box_cfg.get("send_color", "#C9C9C9")

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

    # 아바타 (기본: 옐로우 원 + 글자 / Tone L: config의 avatar_bg·avatar_fg)
    av_margin = (box_h - av_size) // 2
    av_x0 = box_x + av_margin + 8
    av_y0 = box_y + av_margin
    draw.ellipse(
        [(av_x0, av_y0), (av_x0 + av_size, av_y0 + av_size)],
        fill=av_bg,
    )
    av_font = _load_font(font_dir, "NotoSansKR-Bold.ttf", int(av_size * 0.45))
    ax = av_x0 + (av_size - int(_font_w(av_font, av_label))) // 2
    ay = av_y0 + int(av_size * 0.25)
    draw.text((ax, ay), av_label, font=av_font, fill=av_fg)

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
    ], fill=send_color)

    y = box_y + box_h

    # ── CTA (옵션 — Tone L 기본 비활성: 질문 한 줄이 곧 CTA) ────────────────
    if cta_cfg.get("enabled", True):
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


def _draw_blurred_text(
    base: Image.Image,
    xy: tuple[int, int],
    text: str,
    font: ImageFont.FreeTypeFont,
    color: str,
    radius: float,
) -> Image.Image:
    """텍스트를 별도 투명 레이어에 선명하게 그린 뒤 가우시안 블러 적용, base에 합성.

    base: RGBA 이미지 (in-place 합성 후 동일 객체 반환)
    xy: 텍스트 좌상단 좌표 (base 기준)
    radius: 블러 반경(px). 1080폭 기준 1.5~2.5 권장 — 모양은 보이되 읽기는 어려운 정도.
    """
    pad = max(8, int(radius * 4))
    tw = int(_font_w(font, text))
    try:
        ascent, descent = font.getmetrics()
        th = ascent + descent
    except Exception:
        th = int(getattr(font, "size", 32) * 1.4)

    layer = Image.new("RGBA", (tw + pad * 2, th + pad * 2), (0, 0, 0, 0))
    ImageDraw.Draw(layer).text((pad, pad), text, font=font, fill=color)
    if radius > 0:
        layer = layer.filter(ImageFilter.GaussianBlur(radius=radius))

    if base.mode != "RGBA":
        base = base.convert("RGBA")
    base.alpha_composite(layer, (xy[0] - pad, xy[1] - pad))
    return base


_MOSAIC_SHADES: list[str] = ["#ECECEC", "#D8D8D8", "#C2C2C2", "#A6A6A6", "#8C8C8C", "#767676"]


def _draw_mosaic_nickname(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    nickname: str,
    font: ImageFont.FreeTypeFont,
    cell: int = 12,
) -> int:
    """닉네임을 무채색 격자 모자이크로 렌더 — 글자 형태만 어렴풋, 판독 불가.

    클로드 디자인 원본(다시봄 레이아웃 - 댓글.dc.html .rc-mosaic)과 동일하게
    12px 정사각 셀 1행을 그린다. 셀 개수는 실제 닉네임의 렌더 폭에 비례해
    자연스러운 길이 편차를 만들고, seed는 닉네임 문자 합으로 결정해 같은
    작성자는 항상 같은 패턴을 갖는다(매 프레임 재생성 시 깜빡임 방지).

    Returns: 그려진 모자이크의 전체 폭(px) — 이후 요소(BEST 배지 등) 배치용.
    """
    text_w = max(cell * 6, int(_font_w(font, nickname or "익명")))
    n_cells = max(6, min(28, round(text_w / cell)))
    seed = sum(ord(c) for c in (nickname or "익명"))
    x, y = xy
    for i in range(n_cells):
        shade = _MOSAIC_SHADES[(seed + i * 7) % len(_MOSAIC_SHADES)]
        cx = x + i * cell
        draw.rectangle([(cx, y), (cx + cell, y + cell)], fill=shade)
    return n_cells * cell


def _render_comments_frame(
    base_frame: Image.Image,
    comment_items: list[dict],
    layout: dict,
    font_dir: Path,
    out_path: Path,
    content_top: int,
    reveal_count: int | None = None,
    fade_alpha: float = 1.0,
    stage: int | None = None,
) -> Path:
    """씬 comments — 정렬바 + 커뮤니티 댓글 세로 리스트.

    comment_items: [{"author","content","likes","created_at","side","is_best"}]
    필드 누락은 허용 — 없으면 안전한 기본값으로 처리한다.
    reveal_count: 누적 공개 개수(1~N). None이면 전체 표시(레거시 동작).
    fade_alpha: 가장 최근에 새로 공개된 댓글(행) 1개에만 적용하는 불투명도(0~1).
        기본 1.0(완전 불투명, 기존 동작 그대로). 점진 공개 페이드인에 쓰인다.

    ``scenes.comments.row.style == "card"``(Again Spring Tone L 오버라이드)면
    각 댓글이 카드(배경+보더)로 렌더되고, 닉네임에는 미디엄 블러 + 진영 표시
    (``side``가 "author"/"partner"면 ``* 닉네임`` + 피치/세이지)가 적용된다.
    ``row.style`` 미지정(기본 "list")이면 기존 와글 리스트+구분선 렌더를 그대로 유지한다.
    """
    from ai_worker.renderer.layout import _load_font

    theme = _theme_name(layout)
    sc = layout["scenes"]["comments"]
    cw = layout["canvas"]["width"]
    ch = layout["canvas"]["height"]

    if theme == "tone_l":
        palette = layout["global"].get("palette", {})
        pad_x = layout["global"].get("title_block", {}).get("pad_x", 90)
        sort_cfg = sc.get("sort_bar", {})
        cards_cfg = sc.get("cards", {})
        avatar_cfg = sc.get("avatar", {})
        nick_cfg = sc.get("nickname", {})
        text_cfg = sc.get("text", {})
        footer_cfg = sc.get("footer", {})

        max_items = cards_cfg.get("max_items", 3)
        items = comment_items[:max_items]
        visible = items if reveal_count is None else items[:reveal_count]

        img = base_frame.copy()
        draw = ImageDraw.Draw(img)

        sort_fs = sort_cfg.get("font_size", 36)
        sort_font = _load_font(font_dir, "NotoSansKR-Bold.ttf", sort_fs)
        label_font = _load_font(font_dir, "NotoSansKR-Medium.ttf", sort_fs - 8)
        y = content_top + sort_cfg.get("gap_top", 8)
        draw.text((pad_x, y), "댓글 ", font=sort_font, fill=sort_cfg.get("count_color", "#5C4030"))
        prefix_w = int(_font_w(sort_font, "댓글 "))
        count_font = _load_font(font_dir, "NotoSansKR-Bold.ttf", sort_fs)
        draw.text((pad_x + prefix_w, y), str(len(items)), font=count_font,
                  fill=palette.get("peach", "#C9785A"))
        label = str(sort_cfg.get("label", "추천순")).replace("▾", "").replace("▼", "").strip() or "추천순"
        label_color = sort_cfg.get("label_color", "#A08670")
        chevron_size = max(10, sort_fs // 3)
        lbl_w = int(_font_w(label_font, label))
        label_x = cw - pad_x - lbl_w - chevron_size - 10
        draw.text((label_x, y), label, font=label_font, fill=label_color)
        _draw_down_chevron(
            draw,
            center_x=cw - pad_x - chevron_size // 2,
            center_y=y + sort_fs // 2,
            size=chevron_size,
            color=label_color,
        )
        y += int(sort_fs * 1.5)
        divider_color = sort_cfg.get("divider_color", "#E5DED2")
        draw.rectangle([(pad_x, y), (cw - pad_x, y + sort_cfg.get("divider_thickness", 2))],
                       fill=divider_color)
        y += cards_cfg.get("gap_top", 30)

        nick_fs = nick_cfg.get("font_size", 28)
        nick_font = _load_font(font_dir, "NotoSansKR-Bold.ttf", nick_fs)
        text_fs = text_cfg.get("font_size", 36)
        text_font = _load_font(font_dir, "NotoSansKR-Medium.ttf", text_fs)
        text_lh = text_cfg.get("line_height", 52)
        text_max_lines = text_cfg.get("max_lines", 2)
        footer_font = _load_font(font_dir, "NotoSansKR-Regular.ttf", footer_cfg.get("font_size", 26))
        av_d = avatar_cfg.get("size", 72)
        card_pad_x = cards_cfg.get("pad_x", 24)
        card_pad_y = cards_cfg.get("pad_y", 20)
        card_w = cw - 2 * pad_x

        for item in visible:
            author = _sanitize_comment_display_text(item.get("author") or "익명") or "익명"
            side = (item.get("side") or "").strip().lower()
            content = _sanitize_comment_display_text(item.get("content", "") or "")
            likes = item.get("likes", 0) or 0
            is_best = bool(item.get("is_best"))

            text_lines = _wrap_korean(content, text_font, card_w - 2 * card_pad_x - av_d - avatar_cfg.get("gap_right", 16), keep_all=True)[:text_max_lines]
            card_h = card_pad_y + max(av_d, nick_fs + 10) + 10 + len(text_lines) * text_lh + 10 + int(footer_cfg.get("font_size", 26) * 1.4) + card_pad_y

            border_color = cards_cfg.get("best_border", "#C9785A") if is_best else cards_cfg.get("border", "#E5DED2")
            img = _draw_card(img, pad_x, y, card_w, card_h, cards_cfg.get("radius", 24), palette, border_color)
            draw = ImageDraw.Draw(img)

            av_bg = {"author": avatar_cfg.get("author_bg", "#C9785A"),
                     "partner": avatar_cfg.get("partner_bg", "#5F8F76")}.get(side, avatar_cfg.get("neutral_bg", "#A08670"))
            av_x, av_y = pad_x + card_pad_x, y + card_pad_y
            draw.ellipse([(av_x, av_y), (av_x + av_d, av_y + av_d)], fill=av_bg)
            initial = author[0] if author else "익"
            init_font = _load_font(font_dir, "NotoSansKR-Bold.ttf", int(av_d * 0.4))
            draw.text((av_x + (av_d - int(_font_w(init_font, initial))) // 2, av_y + int(av_d * 0.22)),
                      initial, font=init_font, fill=avatar_cfg.get("text_color", "#FFF8F0"))

            tx = av_x + av_d + avatar_cfg.get("gap_right", 16)
            ny = y + card_pad_y
            # 닉네임 — 무채색 격자 모자이크로 익명화(클로드 디자인 .rc-mosaic 참조)
            mosaic_cell = 12
            mosaic_y = ny + max(0, (nick_fs - mosaic_cell) // 2)
            mosaic_w = _draw_mosaic_nickname(draw, (tx, mosaic_y), author, nick_font, mosaic_cell)
            if is_best:
                # BEST 배지 — 모자이크 실측 폭 바로 옆(gap 12px), 같은 행 세로 중앙 정렬
                # (참조: .rc-nickrow{display:flex;align-items:center;gap:12px})
                badge_font = _load_font(font_dir, "NotoSansKR-Bold.ttf", 22)
                badge_w = int(_font_w(badge_font, "BEST")) + 32
                badge_h = 32
                badge_x = tx + mosaic_w + 12
                badge_y = ny + max(0, (nick_fs - badge_h) // 2)
                draw.rounded_rectangle([(badge_x, badge_y), (badge_x + badge_w, badge_y + badge_h)],
                                       radius=8, fill=palette.get("peach", "#C9785A"))
                bw = int(_font_w(badge_font, "BEST"))
                draw.text((badge_x + (badge_w - bw) // 2, badge_y + (badge_h - 22) // 2 - 2),
                          "BEST", font=badge_font, fill="#FFF8F0")

            ty = ny + nick_fs + nick_cfg.get("gap_bottom", 4) + 6
            for line in text_lines:
                draw.text((tx, ty), line, font=text_font, fill=text_cfg.get("color", "#5C4030"))
                ty += text_lh
            foot_text = f"공감 {likes} · {_relative_time(item.get('created_at'))}".rstrip(" ·")
            draw.text((tx, ty + footer_cfg.get("gap_top", 8)), foot_text, font=footer_font,
                      fill=footer_cfg.get("color", "#A08670"))

            y += card_h + cards_cfg.get("gap_between", 24)

        _draw_step_dots(draw, cw, stage or 3, layout)
        _draw_ribbon(draw, cw, ch, layout)
        img.save(str(out_path), "PNG")
        return out_path

    sort_cfg = sc.get("sort_bar", {})
    row_cfg = sc.get("row", {})
    badge_cfg = row_cfg.get("best_badge", {})

    cw = layout["canvas"]["width"]
    ch = layout["canvas"]["height"]

    # 표시 개수 상한 (Again Spring: 3). 미설정(와글)이면 상한 없음 — 기존 동작 유지.
    max_items: int | None = row_cfg.get("max_items")
    if max_items:
        comment_items = comment_items[:max_items]
        if reveal_count is not None:
            reveal_count = min(reveal_count, max_items)

    row_style: str = row_cfg.get("style", "list")

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
    av_font_size = max(14, int(av_d * 0.42))
    av_font = _load_font(font_dir, "NotoSansKR-Bold.ttf", av_font_size)

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

    # Tone L 전용: 닉네임 블러 + 진영색(* 접두). 미설정이면 완전 하위호환.
    nick_blur_radius: float = float(row_cfg.get("nick_blur_radius", 0))
    faction_colors: dict = row_cfg.get("faction_colors") or {}
    show_time: bool = bool(row_cfg.get("show_time", False))

    # 카드 스타일 (row_style == "card") 전용 치수
    card_bg: str = row_cfg.get("card_bg", "#FFFFFF")
    card_border: str = row_cfg.get("card_border", "")
    card_border_w: int = int(row_cfg.get("card_border_width", 1))
    card_radius: int = int(row_cfg.get("card_radius", 14))
    card_gap: int = int(row_cfg.get("card_gap", 18))
    card_pad_x: int = int(row_cfg.get("card_pad_x", 24))

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
    sort_divider_color: str = sort_cfg.get("divider_color", divider_color)

    # 아바타 색상 팔레트 (side 미지정 댓글용 폴백)
    _AV_COLORS = [
        "#4A90D9", "#E67E22", "#27AE60", "#9B59B6",
        "#E74C3C", "#1ABC9C", "#F39C12", "#2980B9",
    ]

    # base_frame 배경은 이미 site theme(글로벌 background_color)이 반영된 상태로 들어온다 —
    # Again Spring(Tone L)은 layout['global']['background_color']=#EDF1E8이 이미 베이킹됨.
    img = base_frame.convert("RGBA").copy()
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

    if row_style == "card":
        y += card_gap // 2
    else:
        # 구분선 (list 스타일)
        draw.rectangle([(0, y), (cw, y + divider_th)], fill=sort_divider_color)
        y += divider_th

    # ── 댓글 행 치수 ──────────────────────────────────────────────────────
    if row_style == "card":
        content_x0 = pad_x + card_pad_x
    else:
        content_x0 = pad_x
    row_text_x = content_x0 + av_d + av_gap
    text_area_w = cw - row_text_x - (pad_x + card_pad_x if row_style == "card" else pad_x)

    # 노출 범위 결정 (reveal_count=None이면 전체)
    visible = comment_items if reveal_count is None else comment_items[:reveal_count]

    def _row_h(item: dict) -> int:
        """댓글 1행이 차지하는 총 세로 폭 측정 (draw 없이). 다음 행 간격 포함."""
        content_text = item.get("content", "")
        c_lines = _wrap_korean(content_text, text_font, text_area_w, keep_all=True)
        n_lines = min(len(c_lines), text_max_lines)
        blur_pad = int(nick_blur_radius * 3) if nick_blur_radius > 0 else 0
        row_inner = max(nick_lh, av_d) + 8 + blur_pad + (n_lines * text_lh) + 8 + footer_lh
        base_h = row_pad_top + row_inner + row_pad_bot
        return base_h + (card_gap if row_style == "card" else divider_th)

    heights = [_row_h(it) for it in visible]
    band_h = (ch - 60) - y  # 정렬바 아래 ~ 하단 여백

    # 최신 항목이 항상 보이도록 오래된 항목부터 drop (bottom-anchor window)
    start = 0
    while sum(heights[start:]) > band_h and start < len(visible) - 1:
        start += 1
    draw_items = visible[start:]
    draw_heights = heights[start:]

    def _display_nick(raw: str | None) -> str:
        """표시용 닉. userId/해시처럼 보이면 익명, 너무 길면 자른다."""
        nick = (raw or "").strip() or "익명"
        compact = "".join(ch for ch in nick.lower() if ch.isalnum())
        if len(compact) >= 24 and all(ch in "0123456789abcdef" for ch in compact):
            return "익명"
        if len(nick) > 12:
            return nick[:12] + "…"
        return nick

    def _nick_and_color(item: dict) -> tuple[str, str, str]:
        """(표시 닉네임, 닉네임 색상, 아바타 색상) — side 기준 진영 표시."""
        base_nick = _display_nick(item.get("author"))
        side = (item.get("side") or "").strip().lower()
        if faction_colors and side in ("author", "partner"):
            faction_color = faction_colors.get(side, nick_color)
            return f"* {base_nick}", faction_color, faction_color
        neutral_color = faction_colors.get("neutral", nick_color) if faction_colors else nick_color
        av_color = _AV_COLORS[hash(item.get("author", "") or "") % len(_AV_COLORS)]
        return base_nick, neutral_color, av_color

    def _draw_comment_row(
        target: Image.Image, item: dict, row_y0: int, row_h: int,
    ) -> tuple[Image.Image, int]:
        """댓글 1행을 target(RGBA)에 그리고 (이미지, 다음 행 시작 y)를 반환."""
        gap = card_gap if row_style == "card" else divider_th
        row_bottom = row_y0 + row_h - gap

        if row_style == "card":
            d0 = ImageDraw.Draw(target)
            try:
                d0.rounded_rectangle(
                    [(pad_x, row_y0), (cw - pad_x, row_bottom)],
                    radius=card_radius, fill=card_bg,
                    outline=(card_border if card_border else None),
                    width=(card_border_w if card_border else 0),
                )
            except TypeError:
                d0.rounded_rectangle(
                    [(pad_x, row_y0), (cw - pad_x, row_bottom)],
                    radius=card_radius, fill=card_bg,
                )

        d = ImageDraw.Draw(target)
        row_y = row_y0 + row_pad_top

        nick_text, resolved_nick_color, av_color = _nick_and_color(item)

        # 아바타 원 (항상 선명 — 블러 없음)
        d.ellipse(
            [(content_x0, row_y), (content_x0 + av_d, row_y + av_d)],
            fill=av_color,
        )
        av_char = (_display_nick(item.get("author")) or "익")[0]
        ax = content_x0 + (av_d - int(_font_w(av_font, av_char))) // 2
        ay = row_y + int(av_d * 0.28)
        d.text((ax, ay), av_char, font=av_font, fill="#FFFFFF")

        # 닉네임 — Tone L: 미디엄 블러(모양은 보이되 읽기 어려움). 와글: 선명(기존 동작).
        if nick_blur_radius > 0:
            target = _draw_blurred_text(
                target, (row_text_x, row_y), nick_text, nick_font,
                resolved_nick_color, nick_blur_radius,
            )
            d = ImageDraw.Draw(target)
        else:
            d.text((row_text_x, row_y), nick_text, font=nick_font, fill=resolved_nick_color)
        nick_w = int(_font_w(nick_font, nick_text))

        if item.get("is_best"):
            badge_x0 = row_text_x + nick_w + 16
            badge_label_w = int(_font_w(badge_font, badge_label))
            badge_x1 = badge_x0 + badge_label_w + badge_px * 2
            badge_y0 = row_y + 2
            badge_y1 = badge_y0 + nick_size + badge_py * 2
            try:
                d.rounded_rectangle(
                    [(badge_x0, badge_y0), (badge_x1, badge_y1)],
                    radius=badge_r, fill=badge_bg,
                )
            except AttributeError:
                d.rectangle(
                    [(badge_x0, badge_y0), (badge_x1, badge_y1)],
                    fill=badge_bg,
                )
            d.text(
                (badge_x0 + badge_px, badge_y0 + badge_py),
                badge_label, font=badge_font, fill=badge_fg,
            )

        # 댓글 본문 (항상 선명 — 블러 없음)
        content_text = item.get("content", "")
        c_lines = _wrap_korean(content_text, text_font, text_area_w, keep_all=True)
        c_lines = c_lines[:text_max_lines]
        blur_pad = int(nick_blur_radius * 3) if nick_blur_radius > 0 else 0
        content_y = row_y + max(nick_lh, av_d) + 8 + blur_pad
        for tl in c_lines:
            tl = tl.replace("\n", " ").replace("\r", " ")
            d.text((row_text_x, content_y), tl, font=text_font, fill=text_color)
            content_y += text_lh

        # 푸터 — 추천수 + (옵션) 상대시간 + 답글. 항상 선명.
        likes = item.get("likes", 0)
        likes_str = _fmt_count(likes) if (likes or 0) > 0 else "0"
        footer_parts = [f"▲  {likes_str}"]
        if show_time:
            rel = _relative_time(item.get("created_at"))
            if rel:
                footer_parts.append(rel)
        footer_parts.append("답글")
        footer_text = "    ".join(footer_parts)
        footer_y = content_y + 8
        d.text((row_text_x, footer_y), footer_text, font=footer_font, fill=footer_color)

        if row_style != "card":
            d.rectangle([(0, row_bottom), (cw, row_bottom + divider_th)], fill=divider_color)

        return target, row_y0 + row_h

    # 점진 공개 페이드: 가장 최근에 새로 드러난 행에만 fade_alpha 적용.
    # (bottom-anchor 윈도잉 후에도 항상 draw_items의 마지막 원소가 최신 항목이다 —
    #  오래된 항목만 앞에서 drop되므로.)
    newest_pos = len(draw_items) - 1 if reveal_count is not None else -1

    for c_i, (item, row_h) in enumerate(zip(draw_items, draw_heights)):
        is_newest_fading = (c_i == newest_pos) and fade_alpha < 0.999
        if is_newest_fading:
            layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
            layer, next_y = _draw_comment_row(layer, item, y, row_h)
            alpha_scale = max(0.0, min(1.0, fade_alpha))
            alpha_ch = layer.split()[3].point(lambda a: int(a * alpha_scale))
            layer.putalpha(alpha_ch)
            img.alpha_composite(layer)
            y = next_y
        else:
            img, y = _draw_comment_row(img, item, y, row_h)

    img = img.convert("RGB")
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
    theme = _theme_name(layout)
    cache_raw = (
        f"{text}"
        f"|{video_text_cfg}"
        f"|{canvas_cfg.get('width')}x{canvas_cfg.get('height')}"
        f"|ct{content_top}"
        f"|theme{theme}"
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
    align, pad_x = _body_align(layout)

    if content_top > 0:
        # 새 디자인: caption_above 기반
        cap_cfg = video_text_cfg.get("caption_above", {})
        font_size: int = cap_cfg.get("font_size", 50)
        lh: int = cap_cfg.get("line_height", 62)
        cap_color: str = cap_cfg.get("color", "#161616")
        cap_pad_top: int = cap_cfg.get("pad_top", 56)
        max_w: int = cap_cfg.get("max_width", 900)
        cap_max_lines: int = cap_cfg.get("max_lines", 2)

        font = _load_font(font_dir, _body_font_file(layout), font_size)
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

        font = _load_font(font_dir, _body_font_file(layout), font_size)
        lines = _wrap_korean(text, font, max_w)[:cap_max_lines]
        total_h = len(lines) * lh
        y_start = ta.get("y", 450) - total_h // 2

    _draw_centered_text(draw, lines, font, y_start, lh, cap_color, cw,
                        align=align, pad_x=pad_x)

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
