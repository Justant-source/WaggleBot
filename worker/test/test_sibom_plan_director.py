"""again_spring sibom_plan scene director tests.

실행: cd WaggleBot && PYTHONPATH=worker:. python3 worker/test/test_sibom_plan_director.py
(또는 worker 컨테이너 / venv)
"""
from __future__ import annotations

import sys
import tempfile
import types
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(ROOT))

# Lightweight stubs so tests run without full worker deps (dotenv/yaml/…).
# 🚨 실제 config.settings를 먼저 시도한다. 스텁을 무조건 심으면 같은 세션에서
#    나중에 도는 테스트(test_sibom_motion 등)가 스텁에 없는 상수를 import하다
#    깨진다(TTS_TEXT_LEAD_SEC). 스텁은 의존성이 없을 때만 쓴다.
_HAVE_REAL_SETTINGS = False
if "config.settings" not in sys.modules:
    try:
        import config.settings  # noqa: F401
        _HAVE_REAL_SETTINGS = True
    except Exception:
        _HAVE_REAL_SETTINGS = False

if "config.settings" not in sys.modules and not _HAVE_REAL_SETTINGS:
    _settings = types.ModuleType("config.settings")
    _settings.EMOTION_TAGS = {}
    _settings.get_domain_setting = lambda *a, **k: "rule_based"
    _settings.VIDEO_GEN_ENABLED = False
    _settings.ASSETS_DIR = ROOT / "assets"
    _settings.MEDIA_DIR = Path("/tmp/wagglebot_media_test")
    _settings.load_pipeline_config = lambda: {}
    _settings.MAX_BODY_CHARS = 200
    _settings.MAX_HOOK_CHARS = 80
    sys.modules.setdefault("config", types.ModuleType("config"))
    sys.modules["config.settings"] = _settings
if "dotenv" not in sys.modules:
    sys.modules["dotenv"] = types.ModuleType("dotenv")
    sys.modules["dotenv"].load_dotenv = lambda *a, **k: None

# Import leaf modules without package __init__ side effects.
import importlib.util


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


_WORKER = Path(__file__).parent.parent
# Preload analyzer + sibom_plan + director as named modules expected by patches
_load("ai_worker.scene.analyzer", _WORKER / "ai_worker/scene/analyzer.py")
_load("ai_worker.scene.sibom_plan", _WORKER / "ai_worker/scene/sibom_plan.py")
# director imports analyzer + settings already stubbed
_director = _load("ai_worker.scene.director", _WORKER / "ai_worker/scene/director.py")


def test_parse_sibom_plan_aliases() -> None:
    from ai_worker.scene.sibom_plan import parse_sibom_plan

    plan = parse_sibom_plan({
        "sibomPlan": [{
            "role": "intro",
            "imageId": "waiting-reply",
            "caption": "읽씹",
            "beatIndex": 0,
            "size": "large",
            "dwell": "hold",
        }],
    })
    assert len(plan) == 1
    assert plan[0]["image_id"] == "waiting-reply"
    assert plan[0]["role"] == "intro"
    print("PASS: test_parse_sibom_plan_aliases")


def test_again_spring_empty_plan_no_metaphor() -> None:
    """Empty sibom_plan → cream intro (no image), never metaphor."""
    from ai_worker.scene.analyzer import ResourceProfile
    from ai_worker.scene.director import SceneDirector

    script = {
        "hook": "훅입니다",
        "body": [
            {"lines": ["본문 한 줄"]},
            {"lines": ["본문 두 줄"]},
        ],
        "closer": "끝",
    }
    profile = ResourceProfile(
        image_count=0, text_length=20, estimated_sentences=2, ratio=0.0, strategy="balanced",
    )
    director = SceneDirector(
        profile=profile,
        images=["/fake/metaphor.png"],  # must be ignored for again_spring
        script=script,
        mood="shock",
        site_code="again_spring",
        variant_config={"metaphor_id": "empty-chair", "sibom_plan": []},
        post_id=1,
    )
    scenes = director.direct()
    assert scenes[0].type == "intro"
    assert scenes[0].image_url is None, f"expected cream-only intro, got {scenes[0].image_url}"
    assert scenes[0].sibom_role is None
    assert all(
        s.image_url is None or "metaphor" not in str(s.image_url)
        for s in scenes
    )
    print("PASS: test_again_spring_empty_plan_no_metaphor")


def test_again_spring_plan_maps_intro_and_peak() -> None:
    from ai_worker.scene.analyzer import ResourceProfile
    from ai_worker.scene.director import SceneDirector

    script = {
        "hook": "훅",
        "body": [
            # 🚨 문장부호로 끝나야 한다. 본문은 sentence screen으로 재분할되므로
            #   "비트0" 같은 토막은 한 화면으로 합쳐지고, 그러면 배정할 body scene이
            #   모자라 punch가 통째로 스킵된다("no free body scene").
            #   → 아래 test_beats_without_sentence_end_merge_into_one_screen 참고.
            {"lines": ["그날 그는 연락을 끊었다."]},
            {"lines": ["나는 사흘을 기다렸다."]},
            {"lines": ["결국 내가 먼저 물었다."]},
        ],
        "closer": "끝",
    }
    plan = [
        {"role": "intro", "image_id": "waiting-reply", "caption": "읽씹", "beat_index": 0,
         "size": "large", "dwell": "hold"},
        {"role": "peak", "image_id": "indignant", "caption": "억울", "beat_index": 1,
         "size": "large", "dwell": "hold"},
        {"role": "punch", "image_id": "stunned", "caption": "헐", "beat_index": 2,
         "size": "small", "dwell": "punch"},
    ]
    profile = ResourceProfile(
        image_count=0, text_length=30, estimated_sentences=3, ratio=0.0, strategy="balanced",
    )

    fake_png = "/tmp/fake_sibom.png"

    def _fake_materialize(image_id, caption, cache_dir):
        return f"{fake_png}.{image_id}"

    with patch("ai_worker.scene.sibom_plan.materialize_sibom_image", side_effect=_fake_materialize):
        director = SceneDirector(
            profile=profile,
            images=[],
            script=script,
            mood="anger",
            site_code="again_spring",
            variant_config={"sibom_plan": plan},
            post_id=99,
        )
        scenes = director.direct()

    intro = scenes[0]
    assert intro.sibom_role == "intro"
    assert intro.sibom_size == "large"
    assert intro.sibom_dwell == "hold"
    assert intro.image_url and "waiting-reply" in intro.image_url

    body = [s for s in scenes if s.type not in ("intro", "outro", "comments", "chat")]
    cards = [s for s in body if s.type == "image_text" and getattr(s, "sibom_role", None)]
    assert cards, "Sibomi beats must be one-clause image_text cards"
    assert all(s.text_lines for s in cards)
    assert {s.sibom_role for s in cards} >= {"peak", "punch"}
    punch = next(s for s in cards if s.sibom_role == "punch")
    assert punch.sibom_shake is True
    tail = "결국 내가 먼저 물었다."
    assert punch.pre_split_lines == [tail] or tail in "".join(str(x) for x in punch.text_lines)

    for s in scenes:
        if s.type in ("comments", "outro", "chat"):
            assert getattr(s, "sibom_role", None) is None
    print("PASS: test_again_spring_plan_maps_intro_and_peak")


def test_non_again_spring_unchanged_distribute() -> None:
    """Non-again_spring still uses distribute_images with provided images."""
    from ai_worker.scene.analyzer import ResourceProfile
    from ai_worker.scene.director import SceneDirector

    script = {
        "hook": "훅",
        "body": [{"lines": ["a"]}, {"lines": ["b"]}],
        "closer": "끝",
    }
    profile = ResourceProfile(
        image_count=1, text_length=10, estimated_sentences=2, ratio=0.5, strategy="balanced",
    )
    director = SceneDirector(
        profile=profile,
        images=["assets/image/intro/mood/humor/humor_intro_01.jpg"],
        script=script,
        mood="humor",
        site_code="dcinside",
        variant_config={},
    )
    scenes = director.direct()
    assert scenes[0].type == "image_text"
    assert scenes[0].image_url is not None
    print("PASS: test_non_again_spring_unchanged_distribute")


def test_apply_sibom_plan_to_body_unit() -> None:
    from ai_worker.scene.director import SceneDecision
    from ai_worker.scene.sibom_plan import apply_sibom_plan_to_body

    scenes = [
        SceneDecision(type="text_only", text_lines=["a"], image_url=None, video_mode="static"),
        SceneDecision(type="text_only", text_lines=["b"], image_url=None, video_mode="static"),
    ]
    plan = [{
        "role": "punch", "image_id": "drained", "caption": "지침",
        "beat_index": 0, "size": "small", "dwell": "punch",
    }]
    with tempfile.TemporaryDirectory() as td:
        with patch(
            "ai_worker.scene.sibom_plan.materialize_sibom_image",
            return_value=str(Path(td) / "drained.png"),
        ):
            apply_sibom_plan_to_body(scenes, plan, Path(td))
    assert len(scenes) == 2
    assert scenes[0].type == "image_text"
    assert scenes[0].sibom_role == "punch"
    assert scenes[0].text_lines == ["a"]
    assert scenes[1].type == "text_only"
    assert scenes[1].sibom_role is None
    assert scenes[1].text_lines == ["b"]
    print("PASS: test_apply_sibom_plan_to_body_unit")


if __name__ == "__main__":
    test_parse_sibom_plan_aliases()
    test_again_spring_empty_plan_no_metaphor()
    test_again_spring_plan_maps_intro_and_peak()
    test_non_again_spring_unchanged_distribute()
    test_apply_sibom_plan_to_body_unit()
    print("\n🎉 all sibom_plan director tests passed")


def test_beats_without_sentence_end_merge_into_one_screen() -> None:
    """문장부호 없는 토막 비트는 한 화면으로 합쳐진다 (설계된 동작).

    본문은 sentence screen으로 재분할된다(`66ef39b` 이후). 따라서 마침표 없는
    토막들은 하나로 합쳐지고, 배정할 body scene이 줄어 뒤쪽 sibom 비트가
    스킵된다("no free body scene"). 이건 버그가 아니라 재분할 설계의 귀결이며,
    프롬프트가 문장 단위 본문을 내놓아야 한다는 요구사항을 고정하기 위한 테스트다.
    """
    from ai_worker.scene.analyzer import ResourceProfile
    from ai_worker.scene.director import SceneDirector

    script = {
        "hook": "훅",
        "body": [{"lines": ["비트0"]}, {"lines": ["비트1"]}, {"lines": ["비트2"]}],
        "closer": "끝",
    }
    plan = [
        {"role": "peak", "image_id": "indignant", "caption": "억울", "beat_index": 1,
         "size": "large", "dwell": "hold"},
        {"role": "punch", "image_id": "stunned", "caption": "헐", "beat_index": 2,
         "size": "small", "dwell": "punch"},
    ]
    profile = ResourceProfile(
        image_count=0, text_length=30, estimated_sentences=3, ratio=0.0, strategy="balanced",
    )

    with patch("ai_worker.scene.sibom_plan.materialize_sibom_image",
               side_effect=lambda image_id, caption, cache_dir: f"/tmp/fake.{image_id}"):
        director = SceneDirector(
            profile=profile, images=[], script=script, mood="anger",
            site_code="again_spring", variant_config={"sibom_plan": plan}, post_id=99,
        )
        scenes = director.direct()

    body = [s for s in scenes if s.type not in ("intro", "outro", "comments", "chat")]
    assert len(body) == 1                                   # 세 토막이 한 화면으로
    roles = {getattr(s, "sibom_role", None) for s in body}
    assert roles == {"peak"}                                # punch는 자리가 없어 스킵
