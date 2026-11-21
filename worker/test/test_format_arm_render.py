"""포맷 실험(arm) 렌더 매개변수 단위 테스트 — comment_count / outro_mode / max_duration_sec.

LLM·TTS·GPU·ffmpeg 불필요. 키가 없을 때 기존 동작과 같은지가 핵심 회귀 기준이다.
"""
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image, ImageChops

from ai_worker.renderer import layout as L
from ai_worker.scene.director import (
    SceneDirector, VOTE_REVEAL_OUTRO_TEXT,
)
from ai_worker.scene.analyzer import ResourceProfile

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]  # 저장소 루트 (host 의 worker/config 는 컨테이너 마운트 지점이라 비어 있다)
FONT_DIR = ROOT / "assets" / "fonts"
BASE_VC = {"pre_scripted": True, "outro_text": "상대방의 사연도 궁금하시죠? 댓글에서 확인해 보세요."}


def _comments():
    return [
        SimpleNamespace(id=i, author=f"user{i}", content=f"댓글 {i}번 내용입니다", likes=10 - i, side="neutral")
        for i in range(1, 5)
    ]


def _direct(monkeypatch, variant_config, **kw):
    monkeypatch.chdir(ROOT)  # direct() 는 cwd 기준 config/scene_policy.json 을 읽는다
    profile = ResourceProfile(image_count=0, text_length=100, estimated_sentences=3, ratio=0.0, strategy="balanced")
    script = {"hook": "훅", "body": [{"line_count": 1, "lines": ["본문 한 줄"]}], "closer": "끝"}
    d = SceneDirector(
        profile, [], script, mood="daily", site_code="again_spring",
        comments=_comments(), variant_config=variant_config,
        outro_text=BASE_VC["outro_text"], comment_voices=[], **kw,
    )
    return d.direct()


def _comment_items(scenes):
    cs = [s for s in scenes if s.type == "comments"]
    return cs[0].comment_items if cs else None


def _outro(scenes):
    return [s for s in scenes if s.type == "outro"][0]


# ── 키 없음 = 기존 동작 ───────────────────────────────────────────────

def test_no_keys_keeps_two_comments_and_original_outro(monkeypatch):
    scenes = _direct(monkeypatch, dict(BASE_VC))
    items = _comment_items(scenes)
    assert [i["author"] for i in items] == ["user1", "user2"]
    assert _outro(scenes).text_lines == [BASE_VC["outro_text"]]


def test_partner_cta_same_as_no_keys(monkeypatch):
    base = _direct(monkeypatch, dict(BASE_VC))
    cta = _direct(monkeypatch, {**BASE_VC, "outro_mode": "partner_cta"})
    assert [s.type for s in base] == [s.type for s in cta]
    assert _outro(cta).text_lines == _outro(base).text_lines
    assert _comment_items(cta) == _comment_items(base)


# ── comment_count ─────────────────────────────────────────────────────

def test_comment_count_zero_has_no_comment_scene(monkeypatch):
    scenes = _direct(monkeypatch, {**BASE_VC, "comment_count": 0})
    assert not any(s.type == "comments" for s in scenes)
    assert scenes[-1].type == "outro"


def test_comment_count_one(monkeypatch):
    items = _comment_items(_direct(monkeypatch, {**BASE_VC, "comment_count": 1}))
    assert [i["author"] for i in items] == ["user1"]


def test_comment_count_invalid_falls_back(monkeypatch):
    for bad in (-1, "2", True, None, 1.5):
        items = _comment_items(_direct(monkeypatch, {**BASE_VC, "comment_count": bad}))
        assert len(items) == 2, bad


def test_layout_cap_helpers():
    assert L._comment_cap({}) == 2
    assert L._comment_cap(None) == 2
    assert L._comment_cap({"comment_count": 0}) == 0
    assert L._comment_cap({"comment_count": 1}) == 1
    assert L._comment_cap({"comment_count": True}) == 2


def test_zero_cap_yields_no_comment_entries_in_plan():
    scene = SimpleNamespace(
        type="comments", text_lines=[], image_url=None, mood="daily", tts_emotion="",
        comment_items=[{"author": "a", "content": "하나", "voice": None}, {"author": "b", "content": "둘", "voice": None}],
        chat_messages=None, dwell_sec=4.0, sfx_events=[], voice_override=None,
    )
    _, plan, _ = L._scenes_to_plan_and_sentences([scene], max_comment_items=0)
    assert [e for e in plan if e["type"] == "comments"] == []
    _, plan2, _ = L._scenes_to_plan_and_sentences([scene], max_comment_items=1)
    assert len([e for e in plan2 if e["type"] == "comments"]) == 1
    _, plan3, _ = L._scenes_to_plan_and_sentences([scene], max_comment_items=None)
    assert len([e for e in plan3 if e["type"] == "comments"]) == 2


# ── outro_mode = vote_reveal ──────────────────────────────────────────

def test_vote_reveal_sets_question_text_and_tts_text(monkeypatch):
    scenes = _direct(monkeypatch, {**BASE_VC, "outro_mode": "vote_reveal"})
    outro = _outro(scenes)
    assert outro.text_lines == [VOTE_REVEAL_OUTRO_TEXT] == ["당신은 어느 쪽인가요?"]
    sentences, plan, _ = L._scenes_to_plan_and_sentences(scenes, max_comment_items=2)
    closer = [s for s in sentences if s["section"] == "closer"]
    assert [s["text"] for s in closer] == ["당신은 어느 쪽인가요?"]  # TTS 낭독 = 화면 문구


def test_vote_reveal_overrides_even_without_base_outro(monkeypatch):
    monkeypatch.chdir(ROOT)
    profile = ResourceProfile(image_count=0, text_length=10, estimated_sentences=1, ratio=0.0, strategy="balanced")
    d = SceneDirector(profile, [], {"hook": "훅", "body": [{"lines": ["본문"]}], "closer": "끝"},
                      mood="daily", site_code="again_spring", comment_voices=[],
                      variant_config={"outro_mode": "vote_reveal"})
    assert _outro(d.direct()).text_lines == ["당신은 어느 쪽인가요?"]


@pytest.fixture(scope="module")
def tone_l_layout():
    cfg = json.loads((ROOT / "config" / "layout.json").read_text(encoding="utf-8"))
    lo = copy.deepcopy(cfg)
    tone_l = lo.get("themes", {}).get("tone_l", {})
    L._deep_merge(lo.setdefault("global", {}), tone_l.get("global", {}))
    L._deep_merge(lo.setdefault("scenes", {}), tone_l.get("scenes", {}))
    lo["global"]["theme"] = "tone_l"
    return lo


def _outro_frame(layout, cfg, tmp_path, name):
    hdr = L._create_header_only_frame(layout, FONT_DIR)
    out = tmp_path / f"{name}.png"
    L._render_outro_frame(hdr, "당신은 어느 쪽인가요?", layout, FONT_DIR, out,
                          render_profile="marketing_v2", cfg=cfg)
    return Image.open(out).convert("RGB")


@pytest.mark.skipif(not (ROOT / "config" / "layout.json").exists(), reason="layout.json missing")
def test_outro_frame_bar_only_with_valid_ratio(tone_l_layout, tmp_path):
    none = _outro_frame(tone_l_layout, {}, tmp_path, "none")
    with_bar = _outro_frame(tone_l_layout, {"empathy_ratio": {"a": 64, "b": 36}}, tmp_path, "bar")
    zero = _outro_frame(tone_l_layout, {"empathy_ratio": {"a": 0, "b": 0}}, tmp_path, "zero")
    missing = _outro_frame(tone_l_layout, {"outro_mode": "vote_reveal"}, tmp_path, "missing")
    garbage = _outro_frame(tone_l_layout, {"empathy_ratio": {"a": "x", "b": None}}, tmp_path, "garbage")
    assert ImageChops.difference(none, with_bar).getbbox() is not None   # 막대가 그려진다
    for img in (zero, missing, garbage):                                  # 비율 없음/0:0/불량 = 문구만, 실패 없음
        assert ImageChops.difference(none, img).getbbox() is None


# ── 길이 초과 시 댓글 제거 ────────────────────────────────────────────

def _plan(n_comments):
    return ([{"type": "intro"}, {"type": "text_only"}, {"type": "text_only"}]
            + [{"type": "comments", "item_idx": k} for k in range(n_comments)]
            + [{"type": "outro"}])


def test_trim_noop_without_comment_count_key():
    plan = _plan(2)
    durs = [5, 20, 20, 6, 6, 4]  # 61s, 한도 25인데도 키가 없으면 건드리지 않는다
    assert L._comment_trim_keep_positions(plan, durs, {"max_duration_sec": 25}) == list(range(6))


def test_trim_noop_without_max_duration():
    plan = _plan(2)
    assert L._comment_trim_keep_positions(plan, [5, 20, 20, 6, 6, 4], {"comment_count": 2}) == list(range(6))


def test_trim_drops_last_comments_first_until_within_slack():
    plan = _plan(2)
    durs = [5, 8, 8, 5, 5, 4]  # 35s, 한도 30 → 32 허용. 뒤 댓글 하나(5s) 빼면 30s
    keep = L._comment_trim_keep_positions(plan, durs, {"max_duration_sec": 30, "comment_count": 2})
    assert keep == [0, 1, 2, 3, 5]  # item_idx 1 이 빠지고 item_idx 0 은 유지


def test_trim_within_slack_keeps_all():
    plan = _plan(2)
    durs = [5, 8, 8, 5, 4, 4]  # 34s, 한도 32
    assert len(L._comment_trim_keep_positions(plan, durs, {"max_duration_sec": 32, "comment_count": 2})) == 6
    durs = [5, 8, 8, 5, 5, 3]  # 34s, 한도 32.0 -> 초과
    assert len(L._comment_trim_keep_positions(plan, durs, {"max_duration_sec": 31, "comment_count": 2})) == 5


def test_trim_stops_when_no_comments_left_and_never_drops_story_or_outro():
    plan = _plan(2)
    durs = [5, 20, 20, 5, 5, 4]
    keep = L._comment_trim_keep_positions(plan, durs, {"max_duration_sec": 10, "comment_count": 2})
    assert keep == [0, 1, 2, 5]
    assert [plan[p]["type"] for p in keep] == ["intro", "text_only", "text_only", "outro"]


def test_trim_ignores_bad_values():
    plan = _plan(1)
    durs = [5, 20, 20, 6, 4]
    for vc in ({"max_duration_sec": 0, "comment_count": 1}, {"max_duration_sec": "30", "comment_count": 1},
               {"max_duration_sec": True, "comment_count": 1}, {"max_duration_sec": 30, "comment_count": True}):
        assert L._comment_trim_keep_positions(plan, durs, vc) == list(range(5)), vc
