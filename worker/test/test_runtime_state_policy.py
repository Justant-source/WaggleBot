"""Regression coverage for marketing runtime-state isolation policy."""
from types import SimpleNamespace

from ai_worker.core import progress
from ai_worker.scene.analyzer import ResourceProfile
from ai_worker.scene.director import SceneDirector


def test_progress_uses_only_progress_namespace(monkeypatch) -> None:
    saved: dict[str, dict] = {}
    monkeypatch.setattr(progress, "get_runtime_state", lambda *_: {"current_phase": 5, "phase_started_at": "old"})
    monkeypatch.setattr(progress, "put_runtime_state", lambda _post, key, value: saved.setdefault(key, value) is not None)

    progress.stamp_progress(100, 5, "TTS")

    assert set(saved) == {"progress"}
    assert saved["progress"]["phase_started_at"] == "old"
    assert saved["progress"]["current_phase"] == 5


def test_pre_scripted_marketing_keeps_top_two_comments() -> None:
    profile = ResourceProfile(
        strategy="text_heavy", image_count=0, text_length=10, estimated_sentences=1, ratio=0.0,
    )
    comments = [
        SimpleNamespace(id=3, author="c", content="third", likes=1),
        SimpleNamespace(id=2, author="b", content="second", likes=10),
        SimpleNamespace(id=1, author="a", content="first", likes=10),
    ]
    director = SceneDirector(
        profile, [], {"hook": "hook", "body": [{"lines": ["body"]}]}, comments=comments,
        site_code="again_spring", variant_config={"pre_scripted": True},
    )
    comment_scene = next(scene for scene in director.direct() if scene.type == "comments")
    assert [item["author"] for item in comment_scene.comment_items] == ["a", "b"]
