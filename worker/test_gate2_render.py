#!/usr/bin/env python3
import sys
sys.path.insert(0, '/home/justant/Data/WaggleBot/worker')

from pathlib import Path
from PIL import Image
import json
from ai_worker.renderer._frames import (
    _render_outro_frame, _render_comments_frame,
    _render_image_text_frame, _render_text_only_frame,
    _create_header_only_frame, _create_breadcrumb_frame,
    _create_base_frame
)
from ai_worker.renderer.layout import load_layout, _get_scenes_list, _load_font

# 레이아웃 로드
layout_path = Path('/home/justant/Data/WaggleBot/config/layout.yaml')
layout = load_layout(layout_path)
font_dir = Path('/home/justant/Data/WaggleBot/assets/fonts')
output_dir = Path('/home/justant/Data/WaggleBot/media/_gate2')

# v2 렌더 프로필 확인
render_profile = 'marketing_v2'

# 테스트 1: 아웃트로 (투표 데이터)
print("1. Rendering outro (v2)...")
header_only_frame = _create_header_only_frame(layout, font_dir)
outro_path = output_dir / "test_outro_v2.png"
try:
    _render_outro_frame(
        header_only_frame,
        "여러분이라면 어떻게 하셨을까요?",
        layout,
        font_dir,
        outro_path,
        render_profile=render_profile,
    )
    print(f"OK: Outro saved to {outro_path}")
except Exception as e:
    print(f"FAIL: Outro - {e}")
    import traceback
    traceback.print_exc()

# 테스트 2: 댓글 씬 v2
print("2. Rendering comments (v2)...")
base_frame = _create_base_frame(layout)
breadcrumb = _create_breadcrumb_frame(layout, "Test Title", font_dir, show_title=False)

comment_items = [
    {
        "author": "User A",
        "side": "author",
        "content": "Author perspective content here.",
        "likes": 45,
        "is_best": False,
        "created_at": "2 hours ago"
    },
    {
        "author": "User B",
        "side": "partner",
        "content": "Partner perspective content here.",
        "likes": 38,
        "is_best": True,
        "created_at": "1 hour ago"
    }
]

comments_path = output_dir / "test_comments_v2.png"
content_top = layout["global"]["header"]["height"] + 20
try:
    _render_comments_frame(
        breadcrumb,
        comment_items,
        layout,
        font_dir,
        comments_path,
        content_top=content_top,
        reveal_count=None,
        stage=3,
        render_profile=render_profile,
    )
    print(f"OK: Comments saved to {comments_path}")
except Exception as e:
    print(f"FAIL: Comments - {e}")
    import traceback
    traceback.print_exc()

# 테스트 3: 본문 씬 (text_only) v2
print("3. Rendering text_only (v2)...")
text_history = [
    {
        "lines": [
            "Text line 1",
            "Text line 2"
        ]
    }
]

text_path = output_dir / "test_text_v2.png"
try:
    _render_text_only_frame(
        breadcrumb,
        text_history,
        layout,
        font_dir,
        text_path,
        content_top=content_top,
        stage=2,
    )
    print(f"OK: Text saved to {text_path}")
except Exception as e:
    print(f"FAIL: Text - {e}")
    import traceback
    traceback.print_exc()

# 테스트 4: 본문 씬 (image_text) v2 (이미지 없음)
print("4. Rendering image_text (v2)...")
image_text_path = output_dir / "test_image_text_v2.png"
try:
    _render_image_text_frame(
        breadcrumb,
        None,  # no image
        "Content text here",
        layout,
        font_dir,
        image_text_path,
        content_top=content_top,
        stage=2,
    )
    print(f"OK: Image_text saved to {image_text_path}")
except Exception as e:
    print(f"FAIL: Image_text - {e}")
    import traceback
    traceback.print_exc()

# fast 버전도 테스트 (변경 없음 확인)
print("\n5. Rendering fast version (verify no change)...")
outro_fast_path = output_dir / "test_outro_fast.png"
try:
    _render_outro_frame(
        header_only_frame,
        "여러분이라면 어떻게 하셨을까요?",
        layout,
        font_dir,
        outro_fast_path,
        render_profile='marketing_fast',
    )
    print(f"OK: Fast outro saved to {outro_fast_path}")
except Exception as e:
    print(f"FAIL: Fast outro - {e}")
    import traceback
    traceback.print_exc()

print("\nAll tests completed!")
print(f"Output directory: {output_dir}")
