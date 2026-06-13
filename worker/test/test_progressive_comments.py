"""점진적 낭독(Progressive Narration) 단위 테스트.

댓글/채팅 씬의 항목당 1개 plan 엔트리 변환 (_scenes_to_plan_and_sentences)과
reveal_count 기반 누적 공개 렌더링 (_render_comments_frame, _render_chat_frame)을 검증한다.

실행 (컨테이너 안에서):
    docker exec env-ai_worker-1 python -m pytest test/test_progressive_comments.py -v
"""
import logging
import sys
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 테스트 픽스처 헬퍼
# ---------------------------------------------------------------------------

def _make_layout() -> dict:
    """실제 config/layout.json을 읽어 반환한다."""
    from ai_worker.renderer.layout import _load_layout
    return _load_layout()


def _make_base_frame() -> Image.Image:
    """테스트용 흰색 1080×1920 베이스 프레임."""
    return Image.new("RGB", (1080, 1920), "#FFFFFF")


def _font_dir() -> Path:
    """assets/fonts 경로."""
    from config.settings import ASSETS_DIR
    return ASSETS_DIR / "fonts"


def _make_comments_scene() -> "SceneDecision":
    """댓글 3개를 담은 SceneDecision."""
    from ai_worker.scene.director import SceneDecision
    return SceneDecision(
        type="comments",
        text_lines=[],
        image_url=None,
        comment_items=[
            {"author": "홍길동", "content": "댓글1 내용입니다", "likes": 10, "is_best": True,  "voice": "manbo"},
            {"author": "김영희", "content": "댓글2 내용입니다", "likes": 5,  "is_best": False, "voice": "yohan"},
            {"author": "이철수", "content": "댓글3 내용입니다", "likes": 2,  "is_best": False, "voice": "manbo"},
        ],
    )


def _make_chat_scene() -> "SceneDecision":
    """채팅 메시지 4개를 담은 SceneDecision."""
    from ai_worker.scene.director import SceneDecision
    return SceneDecision(
        type="chat",
        text_lines=[],
        image_url=None,
        chat_messages=[
            {"sender": "나",   "text": "안녕하세요",         "is_mine": True,  "voice": "yohan"},
            {"sender": "상대", "text": "안녕하세요 반갑습니다", "is_mine": False, "voice": "manbo"},
            {"sender": "나",   "text": "오늘 날씨가 좋네요",   "is_mine": True,  "voice": "yohan"},
            {"sender": "상대", "text": "맞아요 산책하기 좋아요", "is_mine": False, "voice": "manbo"},
        ],
    )


# ---------------------------------------------------------------------------
# 1. 댓글 씬 plan 엔트리 개수 및 item_idx 검증
# ---------------------------------------------------------------------------

def test_comments_plan_entries() -> None:
    """댓글 3개 씬 → plan 엔트리 3개, item_idx 0/1/2, sent_idx 순차 증가."""
    from ai_worker.renderer.layout import _scenes_to_plan_and_sentences

    scene = _make_comments_scene()
    sentences, plan, images = _scenes_to_plan_and_sentences([scene])

    # plan 엔트리 3개
    assert len(plan) == 3, f"plan 길이 기대 3, 실제 {len(plan)}"

    # 모든 엔트리 type=="comments"
    for i, entry in enumerate(plan):
        assert entry["type"] == "comments", \
            f"plan[{i}]['type'] 기대 'comments', 실제 {entry['type']!r}"

    # item_idx 0/1/2 순서
    for expected_idx, entry in enumerate(plan):
        assert entry["item_idx"] == expected_idx, \
            f"plan[{expected_idx}]['item_idx'] 기대 {expected_idx}, 실제 {entry['item_idx']}"

    # sent_idx가 순차적으로 증가 (0, 1, 2)
    sent_idxs = [e["sent_idx"] for e in plan]
    assert sent_idxs == sorted(sent_idxs), \
        f"sent_idx가 순차 증가 아님: {sent_idxs}"
    assert sent_idxs[0] == 0, f"첫 sent_idx 기대 0, 실제 {sent_idxs[0]}"

    log.info("test_comments_plan_entries 통과: plan=%s", plan)


# ---------------------------------------------------------------------------
# 2. 채팅 씬 plan 엔트리 개수 및 item_idx 검증
# ---------------------------------------------------------------------------

def test_chat_plan_entries() -> None:
    """채팅 4개 씬 → plan 엔트리 4개, item_idx 0/1/2/3."""
    from ai_worker.renderer.layout import _scenes_to_plan_and_sentences

    scene = _make_chat_scene()
    sentences, plan, images = _scenes_to_plan_and_sentences([scene])

    assert len(plan) == 4, f"plan 길이 기대 4, 실제 {len(plan)}"

    for i, entry in enumerate(plan):
        assert entry["type"] == "chat", \
            f"plan[{i}]['type'] 기대 'chat', 실제 {entry['type']!r}"
        assert entry["item_idx"] == i, \
            f"plan[{i}]['item_idx'] 기대 {i}, 실제 {entry['item_idx']}"

    log.info("test_chat_plan_entries 통과: plan=%s", plan)


# ---------------------------------------------------------------------------
# 3. voice_override가 item["voice"]와 일치하는지 검증
# ---------------------------------------------------------------------------

def test_voice_override_in_sentences() -> None:
    """각 sentence의 voice_override가 item의 voice 값과 일치해야 한다."""
    from ai_worker.renderer.layout import _scenes_to_plan_and_sentences

    comment_scene = _make_comments_scene()
    chat_scene = _make_chat_scene()
    sentences, plan, images = _scenes_to_plan_and_sentences([comment_scene, chat_scene])

    # 댓글 씬 (3개)
    comment_items = comment_scene.comment_items
    comment_entries = [e for e in plan if e["type"] == "comments"]
    assert len(comment_entries) == 3

    for entry in comment_entries:
        item_idx = entry["item_idx"]
        sent_idx = entry["sent_idx"]
        expected_voice = comment_items[item_idx].get("voice")
        actual_voice = sentences[sent_idx].get("voice_override")
        assert actual_voice == expected_voice, (
            f"댓글 item_idx={item_idx}: voice_override 기대 {expected_voice!r}, "
            f"실제 {actual_voice!r}"
        )

    # 채팅 씬 (4개)
    chat_msgs = chat_scene.chat_messages
    chat_entries = [e for e in plan if e["type"] == "chat"]
    assert len(chat_entries) == 4

    for entry in chat_entries:
        item_idx = entry["item_idx"]
        sent_idx = entry["sent_idx"]
        expected_voice = chat_msgs[item_idx].get("voice")
        actual_voice = sentences[sent_idx].get("voice_override")
        assert actual_voice == expected_voice, (
            f"채팅 item_idx={item_idx}: voice_override 기대 {expected_voice!r}, "
            f"실제 {actual_voice!r}"
        )

    log.info("test_voice_override_in_sentences 통과")


# ---------------------------------------------------------------------------
# 4. _get_scene_for_entry — 여러 엔트리가 동일 scene_idx 공유
# ---------------------------------------------------------------------------

def test_get_scene_for_entry_shared_scene_idx() -> None:
    """댓글 씬의 여러 plan 엔트리가 같은 scene_idx를 공유해도 올바른 SceneDecision을 반환."""
    from ai_worker.renderer.layout import _scenes_to_plan_and_sentences, _get_scene_for_entry
    from ai_worker.scene.director import SceneDecision

    # intro + comments 두 씬
    intro_scene = SceneDecision(
        type="intro",
        text_lines=[{"text": "훅 텍스트", "audio": None}],
        image_url=None,
    )
    comment_scene = _make_comments_scene()

    scenes_list = [intro_scene, comment_scene]
    sentences, plan, images = _scenes_to_plan_and_sentences(scenes_list)

    comment_entries = [e for e in plan if e["type"] == "comments"]
    assert len(comment_entries) == 3, f"댓글 엔트리 기대 3, 실제 {len(comment_entries)}"

    # 모든 댓글 엔트리의 scene_idx는 1 (comment_scene이 index 1)
    for entry in comment_entries:
        assert entry["scene_idx"] == 1, \
            f"scene_idx 기대 1, 실제 {entry['scene_idx']}"

    # _get_scene_for_entry가 comment_scene을 정확히 반환하는지
    for entry in comment_entries:
        found = _get_scene_for_entry(entry, sentences, scenes_list)
        assert found is comment_scene, \
            f"_get_scene_for_entry 반환값이 comment_scene이 아님: {found}"

    log.info("test_get_scene_for_entry_shared_scene_idx 통과")


# ---------------------------------------------------------------------------
# 5. 빈 content/text 항목은 plan 엔트리에서 제외
# ---------------------------------------------------------------------------

def test_empty_content_skipped() -> None:
    """빈 content/text를 가진 항목은 plan 엔트리에 포함되지 않아야 한다."""
    from ai_worker.renderer.layout import _scenes_to_plan_and_sentences
    from ai_worker.scene.director import SceneDecision

    comment_scene = SceneDecision(
        type="comments",
        text_lines=[],
        image_url=None,
        comment_items=[
            {"author": "A", "content": "정상 댓글", "likes": 1, "is_best": False, "voice": "manbo"},
            {"author": "B", "content": "",          "likes": 0, "is_best": False, "voice": "yohan"},  # 빈 content
            {"author": "C", "content": "   ",       "likes": 0, "is_best": False, "voice": "manbo"},  # 공백만
            {"author": "D", "content": "또다른 댓글", "likes": 2, "is_best": False, "voice": "yohan"},
        ],
    )

    chat_scene = SceneDecision(
        type="chat",
        text_lines=[],
        image_url=None,
        chat_messages=[
            {"sender": "나",   "text": "정상 메시지", "is_mine": True,  "voice": "yohan"},
            {"sender": "상대", "text": "",            "is_mine": False, "voice": "manbo"},  # 빈 text
            {"sender": "나",   "text": "또 정상",     "is_mine": True,  "voice": "yohan"},
        ],
    )

    sentences, plan, images = _scenes_to_plan_and_sentences([comment_scene, chat_scene])

    comment_entries = [e for e in plan if e["type"] == "comments"]
    chat_entries    = [e for e in plan if e["type"] == "chat"]

    # 빈 항목 2개 제외 → 정상 댓글 2개만
    assert len(comment_entries) == 2, \
        f"빈 댓글 제거 후 기대 2, 실제 {len(comment_entries)}"

    # 빈 메시지 1개 제외 → 정상 채팅 2개만
    assert len(chat_entries) == 2, \
        f"빈 채팅 제거 후 기대 2, 실제 {len(chat_entries)}"

    log.info("test_empty_content_skipped 통과")


# ---------------------------------------------------------------------------
# 6. _render_comments_frame — reveal_count별 PNG 생성
# ---------------------------------------------------------------------------

def test_render_comments_reveal_count() -> None:
    """reveal_count=1,2,3 각각에 대해 PNG 파일이 생성되어야 한다."""
    from ai_worker.renderer._frames import _render_comments_frame

    layout = _make_layout()
    base_frame = _make_base_frame()
    font_dir = _font_dir()
    content_top = 400  # 임의 콘텐츠 시작 Y

    comment_items = [
        {"author": "홍길동", "content": "첫 번째 댓글입니다", "likes": 15, "is_best": True},
        {"author": "김영희", "content": "두 번째 댓글입니다", "likes": 8,  "is_best": False},
        {"author": "이철수", "content": "세 번째 댓글입니다", "likes": 3,  "is_best": False},
    ]

    out_dir = Path("/tmp")
    reveal_counts = [1, 2, 3]

    for rc in reveal_counts:
        out_path = out_dir / f"test_progressive_comments_reveal{rc}.png"
        result = _render_comments_frame(
            base_frame=base_frame,
            comment_items=comment_items,
            layout=layout,
            font_dir=font_dir,
            out_path=out_path,
            content_top=content_top,
            reveal_count=rc,
        )
        assert out_path.exists(), f"PNG 파일 미생성: {out_path}"
        assert out_path.stat().st_size > 0, f"PNG 파일 크기 0: {out_path}"
        # 반환값이 경로와 일치
        assert result == out_path, f"반환 경로 불일치: {result} != {out_path}"

    log.info(
        "test_render_comments_reveal_count 통과 — 생성 파일: %s",
        [str(out_dir / f"test_progressive_comments_reveal{rc}.png") for rc in reveal_counts],
    )


def test_render_comments_reveal_count_none() -> None:
    """reveal_count=None (레거시 동작) — 전체 표시, PNG 생성."""
    from ai_worker.renderer._frames import _render_comments_frame

    layout = _make_layout()
    base_frame = _make_base_frame()
    font_dir = _font_dir()

    comment_items = [
        {"author": "A", "content": "레거시 댓글1", "likes": 1, "is_best": False},
        {"author": "B", "content": "레거시 댓글2", "likes": 2, "is_best": True},
    ]

    out_path = Path("/tmp/test_progressive_comments_legacy.png")
    _render_comments_frame(
        base_frame=base_frame,
        comment_items=comment_items,
        layout=layout,
        font_dir=font_dir,
        out_path=out_path,
        content_top=400,
        reveal_count=None,
    )
    assert out_path.exists(), f"레거시 PNG 미생성: {out_path}"

    log.info("test_render_comments_reveal_count_none 통과")


# ---------------------------------------------------------------------------
# 7. _render_chat_frame — reveal_count별 PNG 생성
# ---------------------------------------------------------------------------

def test_render_chat_reveal_count() -> None:
    """reveal_count=1,2,4 각각에 대해 PNG 파일이 생성되어야 한다."""
    from ai_worker.renderer._frames import _render_chat_frame

    layout = _make_layout()
    base_frame = _make_base_frame()
    font_dir = _font_dir()
    content_top = 400

    messages = [
        {"sender": "나",   "text": "안녕하세요",           "is_mine": True},
        {"sender": "상대", "text": "안녕하세요 반갑습니다", "is_mine": False},
        {"sender": "나",   "text": "오늘 날씨가 좋네요",   "is_mine": True},
        {"sender": "상대", "text": "맞아요 산책하기 좋아요", "is_mine": False},
    ]

    out_dir = Path("/tmp")
    reveal_counts = [1, 2, 4]

    for rc in reveal_counts:
        out_path = out_dir / f"test_progressive_chat_reveal{rc}.png"
        result = _render_chat_frame(
            base_frame=base_frame,
            messages=messages,
            layout=layout,
            font_dir=font_dir,
            out_path=out_path,
            content_top=content_top,
            reveal_count=rc,
        )
        assert out_path.exists(), f"PNG 파일 미생성: {out_path}"
        assert out_path.stat().st_size > 0, f"PNG 파일 크기 0: {out_path}"
        assert result == out_path, f"반환 경로 불일치: {result} != {out_path}"

    log.info(
        "test_render_chat_reveal_count 통과 — 생성 파일: %s",
        [str(out_dir / f"test_progressive_chat_reveal{rc}.png") for rc in reveal_counts],
    )


def test_render_chat_reveal_count_none() -> None:
    """reveal_count=None (레거시) — 전체 메시지 표시, PNG 생성."""
    from ai_worker.renderer._frames import _render_chat_frame

    layout = _make_layout()
    base_frame = _make_base_frame()
    font_dir = _font_dir()

    messages = [
        {"sender": "나",   "text": "전체 표시 테스트", "is_mine": True},
        {"sender": "상대", "text": "레거시 동작 확인", "is_mine": False},
    ]

    out_path = Path("/tmp/test_progressive_chat_legacy.png")
    _render_chat_frame(
        base_frame=base_frame,
        messages=messages,
        layout=layout,
        font_dir=font_dir,
        out_path=out_path,
        content_top=400,
        reveal_count=None,
    )
    assert out_path.exists(), f"레거시 PNG 미생성: {out_path}"

    log.info("test_render_chat_reveal_count_none 통과")


# ---------------------------------------------------------------------------
# 8. 혼합 씬 (intro + comments + chat) — 전체 plan 일관성
# ---------------------------------------------------------------------------

def test_mixed_scenes_plan_consistency() -> None:
    """intro + comments + chat 혼합 씬에서 plan 엔트리와 sentences의 일관성 검증."""
    from ai_worker.renderer.layout import _scenes_to_plan_and_sentences, _get_scene_for_entry
    from ai_worker.scene.director import SceneDecision

    intro_scene = SceneDecision(
        type="intro",
        text_lines=[{"text": "오늘의 이슈", "audio": None}],
        image_url=None,
    )
    comment_scene = _make_comments_scene()  # 3개
    chat_scene = _make_chat_scene()          # 4개

    scenes_list = [intro_scene, comment_scene, chat_scene]
    sentences, plan, images = _scenes_to_plan_and_sentences(scenes_list)

    # 총 plan 엔트리: intro 1 + comments 3 + chat 4 = 8
    assert len(plan) == 8, f"총 plan 기대 8, 실제 {len(plan)}"

    # 각 엔트리의 sent_idx는 sentences 범위 내
    for i, entry in enumerate(plan):
        sent_idx = entry.get("sent_idx")
        if sent_idx is not None:
            assert 0 <= sent_idx < len(sentences), \
                f"plan[{i}].sent_idx={sent_idx}가 sentences 범위 초과 (len={len(sentences)})"

    # scene_idx별 올바른 SceneDecision 반환 검증
    intro_entries   = [e for e in plan if e["type"] == "intro"]
    comment_entries = [e for e in plan if e["type"] == "comments"]
    chat_entries    = [e for e in plan if e["type"] == "chat"]

    assert len(intro_entries)   == 1
    assert len(comment_entries) == 3
    assert len(chat_entries)    == 4

    # intro 엔트리
    found = _get_scene_for_entry(intro_entries[0], sentences, scenes_list)
    assert found is intro_scene

    # comment 엔트리들
    for entry in comment_entries:
        found = _get_scene_for_entry(entry, sentences, scenes_list)
        assert found is comment_scene, f"댓글 엔트리의 scene이 comment_scene이 아님: {found}"

    # chat 엔트리들
    for entry in chat_entries:
        found = _get_scene_for_entry(entry, sentences, scenes_list)
        assert found is chat_scene, f"채팅 엔트리의 scene이 chat_scene이 아님: {found}"

    log.info("test_mixed_scenes_plan_consistency 통과: total_plan=%d, sentences=%d",
             len(plan), len(sentences))
