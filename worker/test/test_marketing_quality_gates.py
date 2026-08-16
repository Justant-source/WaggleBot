"""Again-Spring marketing quality gates (publish-min sibom, quality error codes)."""
from ai_worker.core.main import _classify_failure
from ai_worker.marketing.quality import requirements


def test_shorts_hard_min_sibom_matches_publish_minimum():
    req = requirements("again_spring", {"pre_scripted": True, "platform_layout": "shorts_standard"})
    assert req is not None
    assert req.min_sibom == 4
    reels = requirements("again_spring", {"pre_scripted": True, "platform_layout": "reels_compact"})
    assert reels.min_sibom == 4


def test_classify_marketing_quality_error_keeps_sibom_code():
    code, stage, retryable = _classify_failure(
        "SIBOM_SCENES_TOO_SHORT: not enough Sibomi images were applied"
    )
    assert code == "SIBOM_SCENES_TOO_SHORT"
    assert stage == "QUALITY_GATE"
    assert retryable is False
