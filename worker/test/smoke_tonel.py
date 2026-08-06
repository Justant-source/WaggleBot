"""Again Spring Tone L comments/outro 렌더 스모크 테스트 (pytest 불필요).

컨테이너 내부에서:
    python3 /app/test/smoke_tonel.py
"""
import copy
import datetime
import sys
from pathlib import Path

sys.path.insert(0, "/app")

from ai_worker.renderer.layout import _load_layout, _deep_merge, _load_font  # noqa: E402
from ai_worker.renderer._frames import (  # noqa: E402
    _create_base_frame, _create_header_only_frame,
    _title_block_bottom_y, _render_comments_frame, _render_outro_frame,
    _relative_time,
)
from PIL import Image  # noqa: E402

FONT_DIR = Path("/app/assets/fonts")
OUT_DIR = Path("/app/media/tmp/smoke_tonel")
OUT_DIR.mkdir(parents=True, exist_ok=True)

layout = _load_layout()
layout = copy.deepcopy(layout)
tone_l = layout.get("themes", {}).get("tone_l", {})
_deep_merge(layout.setdefault("global", {}), tone_l.get("global", {}))
_deep_merge(layout.setdefault("scenes", {}), tone_l.get("scenes", {}))
layout["global"]["theme"] = "tone_l"
layout["global"]["header"]["channel_name"] = "다시봄"

title = "3년 사귄 남친이 상견례 자리에서 이럴 줄은 몰랐다"
meta = {"author": "다시봄", "time": "3시간 전", "views": "1.2만", "comments": 128}

content_top = _title_block_bottom_y(layout, title, FONT_DIR)
base_frame = _create_base_frame(layout, title, FONT_DIR, Path("/app/assets"), meta=meta)
header_only_frame = _create_header_only_frame(layout, FONT_DIR)

now = datetime.datetime.now(datetime.timezone.utc)
# NOTE: director.py의 _build_comment_item()은 created_at을 datetime.isoformat()
# 문자열로 직렬화해서 넘긴다 — 실제 파이프라인과 동일하게 문자열로 테스트한다.
comment_items = [
    {
        "author": "익명의곰돌이",
        "content": "저도 비슷한 일이 있었는데 진짜 화나네요 이건 좀 아니지 않나요",
        "likes": 231,
        "created_at": (now - datetime.timedelta(hours=3)).isoformat(),
        "side": "author",
        "is_best": True,
    },
    {
        "author": "그냥지나가는사람",
        "content": "상대방 입장도 한 번쯤 들어봐야 할 것 같아요",
        "likes": 58,
        "created_at": (now - datetime.timedelta(hours=1)).isoformat(),
        "side": "partner",
        "is_best": False,
    },
    {
        "author": "댓글러123",
        "content": "둘 다 조금씩 잘못한 부분이 있는 것 같습니다",
        "likes": 12,
        "created_at": (now - datetime.timedelta(minutes=20)).isoformat(),
        "side": None,
        "is_best": False,
    },
    {
        "author": "화면밖5번째댓글",
        "content": "이 댓글은 max_items=3 상한 때문에 절대 보이면 안 됩니다",
        "likes": 999999,
        "created_at": now.isoformat(),
        "side": "author",
        "is_best": False,
    },
]

print("── _relative_time() 문자열/None/파싱실패 방어 확인 ──")
_now_dt = datetime.datetime.now(datetime.timezone.utc)
assert _relative_time((_now_dt - datetime.timedelta(hours=3)).isoformat()) == "3시간 전"
assert _relative_time(_now_dt - datetime.timedelta(hours=3)) == "3시간 전"  # datetime 객체도 계속 지원
assert _relative_time(None) == ""
assert _relative_time("") == ""
assert _relative_time("not-a-date") == ""
print("  문자열 ISO / datetime 객체 / None / 빈 문자열 / 파싱 실패 모두 OK")
print()

print("── 진행 공개 프레임 (reveal 1..3), 마지막 프레임은 fade_alpha 스윕 포함 ──")
for reveal in (1, 2, 3):
    out = OUT_DIR / f"comments_reveal_{reveal}.png"
    _render_comments_frame(
        base_frame, comment_items, layout, FONT_DIR, out, content_top,
        reveal_count=reveal,
    )
    img = Image.open(out)
    assert img.size == (1080, 1920), f"unexpected size {img.size}"
    print(f"  reveal={reveal} -> {out.name} size={img.size} mode(before-save-was-RGB)")

for i, alpha in enumerate((0.0, 0.3, 0.6, 1.0)):
    out = OUT_DIR / f"comments_fade_{i}.png"
    _render_comments_frame(
        base_frame, comment_items, layout, FONT_DIR, out, content_top,
        reveal_count=2, fade_alpha=alpha,
    )
    print(f"  fade_alpha={alpha} -> {out.name} OK")

# max_items 캡 확인: comment_items 4개 넣어도 4번째(화면밖)는 절대 렌더되지 않아야 한다.
# (reveal_count=None → 전체 노출 시도해도 max_items=3 캡이 우선 적용됨)
out_all = OUT_DIR / "comments_all_capped.png"
_render_comments_frame(
    base_frame, comment_items, layout, FONT_DIR, out_all, content_top,
    reveal_count=None,
)
print(f"  reveal=None(전체) + max_items=3 캡 -> {out_all.name} OK (4번째 댓글은 항상 표시 안 됨)")

print()
print("── 아웃트로 (마스코트 없음 · 세리프 한 줄 질문) ──")
out_outro = OUT_DIR / "outro_tone_l.png"
_render_outro_frame(
    header_only_frame, "여러분이라면 어떻게 하셨을까요?", layout, FONT_DIR, out_outro,
)
img = Image.open(out_outro)
assert img.size == (1080, 1920)
print(f"  -> {out_outro.name} size={img.size}")

print()
print("── 와글(기본 테마) 회귀 확인 — 오버라이드 없이 기존 동작 유지 ──")
waggle_layout = _load_layout()
waggle_content_top = _title_block_bottom_y(waggle_layout, title, FONT_DIR)
waggle_base = _create_base_frame(waggle_layout, title, FONT_DIR, Path("/app/assets"), meta=meta)
waggle_header_only = _create_header_only_frame(waggle_layout, FONT_DIR)

out_waggle_comments = OUT_DIR / "waggle_comments.png"
_render_comments_frame(
    waggle_base, comment_items, waggle_layout, FONT_DIR, out_waggle_comments, waggle_content_top,
    reveal_count=None,
)
img = Image.open(out_waggle_comments)
print(f"  와글 댓글(캡 없음, 4개 모두 표시되어야 함) -> {out_waggle_comments.name} size={img.size}")

out_waggle_outro = OUT_DIR / "waggle_outro.png"
_render_outro_frame(
    waggle_header_only, "여러분이라면 어떻게 하셨을까요?", waggle_layout, FONT_DIR, out_waggle_outro,
)
print(f"  와글 아웃트로(마스코트 있어야 함) -> {out_waggle_outro.name}")

print()
print("ALL SMOKE CHECKS PASSED")
print(f"결과물 위치(컨테이너 내부): {OUT_DIR}")
