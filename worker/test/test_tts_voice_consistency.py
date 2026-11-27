"""한 영상 안의 낭독·outro·댓글 보이스 일치 + 댓글 풀의 내레이터 제외(해석된 프리셋 기준) 회귀 테스트.

배경(4892a1b 리뷰 BUG 1): 렌더러가 resolve_voice(key, None)(시드 0)로 캐시 키를 만들고 합성은 별도
시드로 해석해 같은 영상에서 낭독 F5 / outro F3처럼 목소리가 갈렸다. 이제 모든 경로가 (키, post_id)로
같은 프리셋을 얻는다. Local-TTS 서버는 호출하지 않는다(synthesize를 가짜로 교체).
"""
import asyncio
from pathlib import Path

import pytest

import config.settings as cfg
from ai_worker.renderer import _tts
from ai_worker.scene.analyzer import ResourceProfile
from ai_worker.scene.director import SceneDirector
from ai_worker.tts import synth
from ai_worker.tts.voice_resolver import LEGACY_GENDER, PRESETS, resolve_voice

pytestmark = pytest.mark.unit


@pytest.fixture()
def fake_tts(monkeypatch, tmp_path):
    """synthesize를 가짜로, ffprobe/ffmpeg 후처리를 no-op으로 교체하고 호출 기록을 돌려준다."""
    calls: list[dict] = []

    async def fake_synthesize(text, scene_type="image_text", voice_key=None, output_path=None,
                              emotion="", post_id=None):
        # 실제 synthesize와 같은 해석 — 서버에 실제로 나가는 프리셋
        calls.append({"scene": scene_type, "key": voice_key, "post_id": post_id,
                      "voice": resolve_voice(voice_key, post_id)})
        Path(output_path).write_bytes(b"x" * 2048)
        return Path(output_path)

    monkeypatch.setattr(synth, "synthesize", fake_synthesize)
    monkeypatch.setattr(_tts, "_get_audio_duration", lambda p: 1.0)
    monkeypatch.setattr(_tts, "_loudnorm_inplace", lambda p: None)
    monkeypatch.setattr(cfg, "MEDIA_DIR", tmp_path / "media")
    return calls


def _chunk(text, idx, tmp_path, scene, key, post_id):
    out = tmp_path / f"out_{scene}_{idx}"
    out.mkdir(parents=True, exist_ok=True)
    return asyncio.run(_tts._tts_chunk_async(text, idx, out, scene, None, key, post_id=post_id))


def _find_seed_where_legacy_differs_from_seed0(key="yura"):
    """레거시 키가 post_id 시드와 시드 0에서 서로 다른 프리셋이 되는 post_id (버그 재현 조건)."""
    for pid in range(1, 200):
        if resolve_voice(key, pid) != resolve_voice(key, None):
            return pid
    raise AssertionError("재현용 post_id를 찾지 못함")


def test_outro_and_narration_use_same_preset_for_legacy_key(fake_tts, tmp_path):
    pid = _find_seed_where_legacy_differs_from_seed0("yura")
    narr_preset = resolve_voice("yura", pid)       # 낭독이 쓰는 프리셋
    assert narr_preset != resolve_voice("yura", None)  # 예전 버그: 캐시/합성이 시드 0과 섞임

    _chunk("다음 영상도 기대해 주세요", 1, tmp_path, "outro", "yura", pid)
    assert fake_tts[-1]["voice"] == narr_preset
    # 캐시 파일 이름도 같은 프리셋 기준 — 시드 0 프리셋으로 만들어지지 않는다
    cached = list((tmp_path / "media" / "audio" / "outro_cache").glob("*.wav"))
    assert len(cached) == 1 and cached[0].name.startswith(f"{narr_preset}_")


def test_outro_cache_hit_is_not_shared_across_different_resolved_presets(fake_tts, tmp_path):
    """같은 문구라도 post마다 해석된 프리셋이 다르면 캐시를 섞지 않는다(남의 목소리 재사용 방지)."""
    pids = {}
    for pid in range(1, 200):
        pids.setdefault(resolve_voice("yura", pid), pid)
        if len(pids) >= 2:
            break
    (pa, a), (pb, b) = list(pids.items())[:2]
    _chunk("고정 클로징", 1, tmp_path, "outro", "yura", a)
    _chunk("고정 클로징", 2, tmp_path, "outro", "yura", b)
    assert [c["voice"] for c in fake_tts] == [pa, pb]          # 두 번 다 실제 합성(캐시 오염 없음)


def test_comment_cache_keyed_by_synthesized_preset(fake_tts, tmp_path):
    pid = _find_seed_where_legacy_differs_from_seed0("manu")
    want = resolve_voice("manu", pid)
    _chunk("댓글입니다", 1, tmp_path, "comments", "manu", pid)
    assert fake_tts[-1]["voice"] == want
    n = len(fake_tts)
    _chunk("댓글입니다", 2, tmp_path, "comments", want, pid)    # 프리셋 키로 다시 → 캐시 히트
    assert len(fake_tts) == n


def test_explicit_preset_unchanged_regardless_of_post_id(fake_tts, tmp_path):
    for pid in (None, 1, 777):
        _chunk("본문", 1, tmp_path, "outro", "m3", pid)
        assert fake_tts[-1]["voice"] == "M3"


def test_pipeline_path_different_legacy_keys_never_disagree_with_none(fake_tts, tmp_path):
    """회귀: 낭독(post_id 해석)·outro(렌더러)가 어떤 레거시 키/post_id 조합에서도 같은 프리셋."""
    for key in list(LEGACY_GENDER)[:12] + ["default"]:
        for pid in (3, 41, 10062262, 10062359):
            narration = resolve_voice(key, pid)
            txt = f"클로징 {key} {pid}"   # 문구를 달리해 캐시 히트 없이 매번 실제 합성 경로를 탄다
            _chunk(txt, 1, tmp_path, "outro", key, pid)
            assert fake_tts[-1]["voice"] == narration, (key, pid)
            # 파이프라인이 한 번 확정한 프리셋을 넘겨도(post_id 유무와 무관하게) 그대로
            n = len(fake_tts)
            _chunk(txt, 2, tmp_path, "outro", narration, pid)       # 같은 프리셋 → 캐시 히트, 재합성 없음
            _chunk(txt, 3, tmp_path, "outro", narration, None)
            assert len(fake_tts) == n


# ── director: 댓글 풀에서 내레이터를 해석된 프리셋 기준으로 제외 ──────────────

def _profile():
    return ResourceProfile(
        image_count=0, text_length=20, estimated_sentences=2, ratio=0.0, strategy="balanced",
    )


def _mk(narrator, pool, post_id):
    return SceneDirector(_profile(), [], {"hook": "h", "body": [], "closer": "c"},
                         comment_voices=pool, post_id=post_id, narrator_voice=narrator)


def test_director_resolves_narrator_and_pool_to_presets():
    d = _mk("yura", ["manu", "F2", "kangil_ref"], post_id=12)
    assert d.narrator_voice == resolve_voice("yura", 12)
    assert all(v in PRESETS for v in d.comment_voices)


def test_director_never_gives_comments_the_resolved_narrator_voice():
    """원시 키 문자열이 달라도(예: 'F5' vs 'yura') 해석된 프리셋이 같으면 풀에서 제외한다."""
    hits = 0
    for pid in range(1, 400):
        narr_preset = resolve_voice("yura", pid)
        # 풀에 내레이터와 '같은 프리셋'이 되는 프리셋 키 + 다른 프리셋 하나
        other = next(p for p in PRESETS if p != narr_preset)
        d = _mk("yura", [narr_preset, other], post_id=pid)
        for author in ("a", "b", "c", "d", "e", "f"):
            assert d._assign_comment_voice(author) == other, (pid, author)
        hits += 1
    assert hits


def test_director_pool_only_narrator_falls_back_to_pool():
    d = _mk("F3", ["yura"], post_id=5)
    pool = d.comment_voices
    assert d._assign_comment_voice("x") in pool      # 제외 후 비면 풀 전체로 폴백(기존 동작 유지)


def test_director_none_narrator_stays_none():
    d = _mk(None, ["F1", "M2"], post_id=5)
    assert d.narrator_voice is None
