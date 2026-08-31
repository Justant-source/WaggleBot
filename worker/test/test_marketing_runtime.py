"""Focused coverage for Again Spring critical-path behavior."""
from types import SimpleNamespace

from ai_worker.core.main import _post_priority
from ai_worker.core.processor import _deterministic_marketing_script
from ai_worker.scene.analyzer import ResourceProfile
from ai_worker.scene.director import SceneDirector


def test_again_spring_has_priority() -> None:
    assert _post_priority(SimpleNamespace(site_code="again_spring")) < _post_priority(
        SimpleNamespace(site_code="dcinside")
    )


def test_pre_scripted_path_avoids_empty_llm_shape() -> None:
    post = SimpleNamespace(title="주말 드라이브 약속", content="첫 문장입니다. 두 번째 문장입니다.")
    script = _deterministic_marketing_script(post, "seohyeon")
    assert script.hook == "주말 드라이브 약속"
    assert script.narrator_voice == "seohyeon"
    assert script.body


def test_comment_voice_is_stable_for_same_author() -> None:
    profile = ResourceProfile(
        strategy="text_heavy", image_count=0, text_length=0, estimated_sentences=1, ratio=0.0,
    )
    first = SceneDirector(profile, [], {}, comment_voices=["a", "b"], narrator_voice="n")
    second = SceneDirector(profile, [], {}, comment_voices=["a", "b"], narrator_voice="n")
    assert first._assign_comment_voice("same-author") == second._assign_comment_voice("same-author")
