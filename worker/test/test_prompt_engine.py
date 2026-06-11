"""Video Prompt Engine 테스트 (LTX-2 V3).

실행 방법:
  # LLM(llm-worker 또는 Anthropic API) 사용 가능 상태에서 전체:
  docker compose exec ai_worker python -m pytest test/test_prompt_engine.py -v

  # LLM 없이 mock 테스트만:
  python -m pytest test/test_prompt_engine.py -v -k "not requires"

V3 변경: generate_prompt는 LLM 실패 시 예외 대신 결정적 폴백을 반환하므로,
실 LLM 게이트 프로브는 transport.call_llm 직접 핑으로 판정한다.
"""
import logging
from pathlib import Path
from unittest.mock import MagicMock

import pytest

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path("test/test_prompt_engine_output")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# 검증 통과용 정상 프롬프트 샘플 (영어, 40자 이상, 메타 마커/물음표 없음)
_VALID_T2V = (
    "A medium shot of a Korean office worker typing at his desk in soft daylight; "
    "he pauses, leans back, and glances toward the window as papers settle. "
    "Quiet keyboard clicks and distant traffic hum underneath."
)
_VALID_BRIEF = (
    "A young Korean woman sits at a cafe table holding a ceramic cup, "
    "soft window daylight falling across her from the left."
)
# 실측 유출 사례 (test_prompt_engine_output/generated_prompts.txt 에서 발췌)
_META_LEAK_1 = (
    "I appreciate the detailed creative brief, but I need to clarify my actual "
    "role here. I'm Kiro, an AI assistant made by Anthropic to help with "
    "development, analysis, planning, and professional work."
)
_META_LEAK_2 = (
    "I'm Kiro, an AI agent built to help you with development, writing, analysis, "
    "and professional work. Could you finish the Korean text or provide the full "
    "story you want me to turn into a video prompt?"
)


def _llm_available() -> bool:
    """실 LLM 백엔드 접속 가능 여부 (call_llm 직접 핑)."""
    try:
        from ai_worker.llm.transport import call_llm
        reply = call_llm(
            "Reply with the single word: ok",
            call_type="raw", max_tokens=8, timeout=20,
        )
        return len(reply) > 0
    except Exception:
        return False


_LLM_OK = _llm_available()

requires_llm = pytest.mark.skipif(
    not _LLM_OK, reason="LLM backend not available (Docker 환경에서 실행하세요)"
)


def _patch_llm(monkeypatch, responses):
    """prompt_engine.call_llm을 시퀀스 응답 fake로 교체하고 호출 기록을 반환한다.

    responses의 원소가 Exception이면 해당 호출에서 raise.
    초과 호출은 마지막 원소를 반복 사용.
    """
    calls: list[dict] = []

    def fake(prompt, **kwargs):
        idx = min(len(calls), len(responses) - 1)
        calls.append({"prompt": prompt, **kwargs})
        result = responses[idx]
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr("ai_worker.video.prompt_engine.call_llm", fake)
    return calls


def _make_scene(video_mode="t2v", tts_sec=4.5, init_image=None, category=None):
    """generate_batch용 Mock 씬."""
    scene = MagicMock()
    scene.video_mode = video_mode
    scene.text_lines = [{"text": "테스트 대사입니다", "audio": None}]
    scene.estimated_tts_sec = tts_sec
    scene.video_init_image = init_image
    scene.video_image_category = category
    return scene


# ──────────────────────────────────────────────
# 출력 검증 (mock, LLM 불필요)
# ──────────────────────────────────────────────

class TestValidatePrompt:

    def test_valid_prompt_passes(self):
        from ai_worker.video.prompt_engine import _validate_prompt
        ok, reason = _validate_prompt(_VALID_T2V)
        assert ok, reason

    def test_meta_leak_fixture_1_rejected(self):
        """실측 유출 사례 1 ('I'm Kiro...')이 차단된다."""
        from ai_worker.video.prompt_engine import _validate_prompt
        ok, reason = _validate_prompt(_META_LEAK_1)
        assert not ok
        assert reason.startswith("meta_marker")

    def test_meta_leak_fixture_2_rejected(self):
        """실측 유출 사례 2 (되물음)가 차단된다."""
        from ai_worker.video.prompt_engine import _validate_prompt
        ok, reason = _validate_prompt(_META_LEAK_2)
        assert not ok

    def test_korean_rejected(self):
        from ai_worker.video.prompt_engine import _validate_prompt
        ok, reason = _validate_prompt(
            "A wide shot of 서울 street at night with neon-free natural lighting and ambient sound."
        )
        assert not ok
        assert reason == "korean_text"

    def test_question_mark_rejected(self):
        from ai_worker.video.prompt_engine import _validate_prompt
        ok, reason = _validate_prompt(
            "A medium shot of a Korean man at a desk. What should happen next in the scene? "
            "The camera holds still with ambient room tone while he waits in silence."
        )
        assert not ok
        assert reason == "question_mark"

    def test_too_short_rejected(self):
        from ai_worker.video.prompt_engine import _validate_prompt
        ok, reason = _validate_prompt("Too short.")
        assert not ok
        assert reason == "too_short"

    def test_too_long_rejected(self):
        from ai_worker.video.prompt_engine import _validate_prompt
        ok, reason = _validate_prompt("a" * 1700)
        assert not ok
        assert reason == "too_long"

    def test_verbose_but_valid_passes(self):
        """1600자 이내의 장황한 정상 프롬프트는 통과한다 (E2E 튜닝: 1200→1600)."""
        from ai_worker.video.prompt_engine import _validate_prompt
        ok, _reason = _validate_prompt((_VALID_T2V + " ") * 6)  # ~1400자
        assert ok


class TestHelpers:

    def test_clamp_duration(self):
        from ai_worker.video.prompt_engine import _clamp_duration
        assert _clamp_duration(0.0) == 4.0
        assert _clamp_duration(2.5) == 4.0
        assert _clamp_duration(4.5) == 4.5
        assert _clamp_duration(8.0) == 6.0

    def test_extract_shot_type(self):
        from ai_worker.video.prompt_engine import _extract_shot_type
        assert _extract_shot_type(_VALID_T2V) == "medium shot"
        assert _extract_shot_type("An extreme close-up of a hand.") == "extreme close-up"
        assert _extract_shot_type("No framing keyword here.") is None

    def test_fallback_prompts_all_moods_valid(self):
        """9개 mood 폴백 프롬프트 전부가 자체 검증을 통과한다."""
        from ai_worker.video.prompt_engine import (
            _FALLBACK_PROMPTS, _FALLBACK_I2V, _validate_prompt,
        )
        moods = {"humor", "touching", "anger", "sadness", "horror",
                 "info", "controversy", "daily", "shock"}
        assert moods == set(_FALLBACK_PROMPTS.keys())
        for mood, prompt in _FALLBACK_PROMPTS.items():
            ok, reason = _validate_prompt(prompt)
            assert ok, f"{mood} 폴백 검증 실패: {reason}"
        ok, reason = _validate_prompt(_FALLBACK_I2V)
        assert ok, reason


# ──────────────────────────────────────────────
# 재시도 → 폴백 흐름 (mock)
# ──────────────────────────────────────────────

class TestRetryAndFallback:

    def test_first_attempt_valid_no_retry(self, monkeypatch):
        from ai_worker.video.prompt_engine import VideoPromptEngine
        calls = _patch_llm(monkeypatch, [_VALID_T2V])
        engine = VideoPromptEngine()
        prompt = engine.generate_prompt(["대사"], "daily", title="제목")
        assert prompt == _VALID_T2V
        assert len(calls) == 1

    def test_meta_response_retried_then_adopted(self, monkeypatch):
        """1차 메타 응답 → 재시도(_RETRY_SUFFIX 포함) → 2차 정상 채택."""
        from ai_worker.video.prompt_engine import VideoPromptEngine, _RETRY_SUFFIX
        calls = _patch_llm(monkeypatch, [_META_LEAK_1, _VALID_T2V])
        engine = VideoPromptEngine()
        prompt = engine.generate_prompt(["대사"], "daily", title="제목")
        assert prompt == _VALID_T2V
        assert len(calls) == 2
        assert calls[1]["prompt"].endswith(_RETRY_SUFFIX)

    def test_korean_failure_retry_includes_specific_hint(self, monkeypatch):
        """한글 포함 실패 시 재시도 지시문에 사유별 보강 힌트가 붙는다."""
        from ai_worker.video.prompt_engine import VideoPromptEngine
        korean_resp = (
            "A wide shot of 서울 street at night with natural lighting, ambient "
            "traffic sound and quiet footsteps in the distance."
        )
        calls = _patch_llm(monkeypatch, [korean_resp, _VALID_T2V])
        prompt = VideoPromptEngine().generate_prompt(["대사"], "daily")
        assert prompt == _VALID_T2V
        assert "never quote the Korean" in calls[1]["prompt"]

    def test_double_failure_returns_fallback(self, monkeypatch):
        """2회 연속 메타 응답 → mood 폴백 프롬프트 반환, 예외 없음."""
        from ai_worker.video.prompt_engine import VideoPromptEngine, _FALLBACK_PROMPTS
        calls = _patch_llm(monkeypatch, [_META_LEAK_1, _META_LEAK_2])
        engine = VideoPromptEngine()
        prompt = engine.generate_prompt(["대사"], "horror", title="제목")
        assert prompt == _FALLBACK_PROMPTS["horror"]
        assert len(calls) == 2

    def test_transport_error_returns_fallback(self, monkeypatch):
        """LLM 전송 오류도 폴백으로 흡수 — 예외를 던지지 않는다."""
        from ai_worker.video.prompt_engine import VideoPromptEngine, _FALLBACK_PROMPTS
        _patch_llm(monkeypatch, [ConnectionError("down"), ConnectionError("down")])
        engine = VideoPromptEngine()
        prompt = engine.generate_prompt(["대사"], "daily")
        assert prompt == _FALLBACK_PROMPTS["daily"]

    def test_i2v_fallback_is_generic_motion(self, monkeypatch):
        from ai_worker.video.prompt_engine import VideoPromptEngine, _FALLBACK_I2V
        _patch_llm(monkeypatch, [_META_LEAK_1, _META_LEAK_2])
        engine = VideoPromptEngine()
        prompt = engine.generate_prompt(["대사"], "daily", has_init_image=True)
        assert prompt == _FALLBACK_I2V


# ──────────────────────────────────────────────
# 동적 입력부 구성 (mock)
# ──────────────────────────────────────────────

class TestPromptComposition:

    def test_t2v_dynamic_blocks_injected(self, monkeypatch):
        """길이/앵커/직전 샷/스토리 컨텍스트가 user prompt에 주입된다."""
        from ai_worker.video import prompt_engine as pe
        calls = _patch_llm(monkeypatch, [_VALID_T2V])
        engine = pe.VideoPromptEngine()
        engine.generate_prompt(
            ["반전 대사"], "shock", title="충격 썰", body_summary="전체 줄거리 요약",
            duration_sec=5.0,
            visual_anchor="A Korean man in his 30s wearing a grey hoodie.",
            prev_shot_type="medium shot",
        )
        user_prompt = calls[0]["prompt"]
        assert "about 5 seconds" in user_prompt
        assert "VISUAL ANCHOR" in user_prompt
        assert "grey hoodie" in user_prompt
        assert "Previous clip framing: medium shot" in user_prompt
        assert "충격 썰" in user_prompt
        assert "전체 줄거리 요약" in user_prompt
        assert "반전 대사" in user_prompt
        # 정적 system은 T2V V3 템플릿
        assert calls[0]["system"] == pe._T2V_SYSTEM_V3
        assert calls[0]["cache_prefix"] is True
        assert calls[0]["call_type"] == "video_prompt_t2v"

    def test_t2v_duration_clamped_in_prompt(self, monkeypatch):
        from ai_worker.video.prompt_engine import VideoPromptEngine
        calls = _patch_llm(monkeypatch, [_VALID_T2V])
        VideoPromptEngine().generate_prompt(["대사"], "daily", duration_sec=9.9)
        assert "about 6 seconds" in calls[0]["prompt"]

    def test_i2v_brief_injected(self, monkeypatch):
        """vision brief가 있으면 'WHAT THE IMAGE SHOWS'로 주입된다."""
        from ai_worker.video import prompt_engine as pe
        calls = _patch_llm(monkeypatch, [_VALID_BRIEF])
        engine = pe.VideoPromptEngine()
        engine.generate_prompt(
            ["대사"], "touching", has_init_image=True,
            image_brief="A woman holds a cup at a cafe table.",
        )
        user_prompt = calls[0]["prompt"]
        assert "WHAT THE IMAGE SHOWS" in user_prompt
        assert "holds a cup" in user_prompt
        assert calls[0]["system"] == pe._I2V_SYSTEM_V3
        assert calls[0]["call_type"] == "video_prompt_i2v"

    def test_i2v_category_hint_fallback(self, monkeypatch):
        """brief 없음 + category 있음 → 카테고리 힌트 주입."""
        from ai_worker.video.prompt_engine import VideoPromptEngine
        calls = _patch_llm(monkeypatch, [_VALID_BRIEF])
        VideoPromptEngine().generate_prompt(
            ["대사"], "daily", has_init_image=True, image_category="photo",
        )
        assert "Category hint: photo" in calls[0]["prompt"]

    def test_simplify_keeps_anchor_instruction(self, monkeypatch):
        from ai_worker.video.prompt_engine import VideoPromptEngine
        calls = _patch_llm(monkeypatch, [_VALID_T2V])
        result = VideoPromptEngine().simplify_prompt(
            _VALID_T2V + " Extra detail sentence.", visual_anchor="anchor text",
        )
        assert "Keep the same protagonist appearance" in calls[0]["prompt"]
        assert result == _VALID_T2V

    def test_simplify_failure_returns_original(self, monkeypatch):
        from ai_worker.video.prompt_engine import VideoPromptEngine
        original = _VALID_T2V
        _patch_llm(monkeypatch, [ConnectionError("down")])
        assert VideoPromptEngine().simplify_prompt(original) == original


# ──────────────────────────────────────────────
# generate_batch: 앵커 1회 + vision brief + 비활성 플래그 (mock)
# ──────────────────────────────────────────────

class TestGenerateBatch:

    def test_anchor_called_once_for_t2v_post(self, monkeypatch):
        from ai_worker.video.prompt_engine import VideoPromptEngine
        monkeypatch.setattr(
            "ai_worker.video.prompt_engine.llm_backend_supports_vision", lambda: False,
        )
        calls = _patch_llm(monkeypatch, [_VALID_T2V])
        scenes = [_make_scene("t2v") for _ in range(3)]
        VideoPromptEngine().generate_batch(scenes, "daily", title="제목", body_summary="요약")
        anchor_calls = [c for c in calls if c.get("call_type") == "video_visual_anchor"]
        assert len(anchor_calls) == 1
        assert all(s.video_prompt for s in scenes)

    def test_anchor_failure_continues_without_anchor(self, monkeypatch):
        """앵커 생성 실패 시 빈 앵커로 진행, 씬 프롬프트는 정상 생성."""
        from ai_worker.video.prompt_engine import VideoPromptEngine

        def fake(prompt, **kwargs):
            if kwargs.get("call_type") == "video_visual_anchor":
                raise ConnectionError("down")
            return _VALID_T2V

        monkeypatch.setattr("ai_worker.video.prompt_engine.call_llm", fake)
        monkeypatch.setattr(
            "ai_worker.video.prompt_engine.llm_backend_supports_vision", lambda: False,
        )
        scenes = [_make_scene("t2v")]
        VideoPromptEngine().generate_batch(scenes, "daily", title="제목")
        assert scenes[0].video_prompt == _VALID_T2V

    def test_no_anchor_for_i2v_only_post(self, monkeypatch):
        from ai_worker.video.prompt_engine import VideoPromptEngine
        monkeypatch.setattr(
            "ai_worker.video.prompt_engine.llm_backend_supports_vision", lambda: False,
        )
        calls = _patch_llm(monkeypatch, [_VALID_BRIEF])
        scenes = [_make_scene("i2v", init_image="/tmp/x.jpg", category="photo")]
        VideoPromptEngine().generate_batch(scenes, "daily", title="제목")
        anchor_calls = [c for c in calls if c.get("call_type") == "video_visual_anchor"]
        assert len(anchor_calls) == 0

    def test_vision_brief_used_when_supported(self, monkeypatch, tmp_path):
        """vision 지원 시 brief 호출에 이미지가 전달되고 결과가 주입된다."""
        from ai_worker.video.prompt_engine import VideoPromptEngine
        img = tmp_path / "init.jpg"
        img.write_bytes(b"fake-jpg-bytes")
        monkeypatch.setattr(
            "ai_worker.video.prompt_engine.llm_backend_supports_vision", lambda: True,
        )

        calls: list[dict] = []

        def fake(prompt, **kwargs):
            calls.append({"prompt": prompt, **kwargs})
            if kwargs.get("call_type") == "video_image_brief":
                assert kwargs.get("images") == [img]
                return _VALID_BRIEF
            return _VALID_T2V

        monkeypatch.setattr("ai_worker.video.prompt_engine.call_llm", fake)
        scenes = [_make_scene("i2v", init_image=str(img))]
        VideoPromptEngine().generate_batch(scenes, "touching", title="제목")

        brief_calls = [c for c in calls if c.get("call_type") == "video_image_brief"]
        assert len(brief_calls) == 1
        i2v_calls = [c for c in calls if c.get("call_type") == "video_prompt_i2v"]
        assert "WHAT THE IMAGE SHOWS" in i2v_calls[0]["prompt"]

    def test_vision_disabled_after_first_failure(self, monkeypatch, tmp_path):
        """첫 brief 실패 시 post 내 잔여 vision 호출이 생략된다."""
        from ai_worker.video.prompt_engine import VideoPromptEngine
        img1 = tmp_path / "a.jpg"
        img2 = tmp_path / "b.jpg"
        img1.write_bytes(b"x")
        img2.write_bytes(b"y")
        monkeypatch.setattr(
            "ai_worker.video.prompt_engine.llm_backend_supports_vision", lambda: True,
        )

        calls: list[dict] = []

        def fake(prompt, **kwargs):
            calls.append({"prompt": prompt, **kwargs})
            if kwargs.get("call_type") == "video_image_brief":
                raise RuntimeError("vision unsupported by proxy")
            return _VALID_BRIEF

        monkeypatch.setattr("ai_worker.video.prompt_engine.call_llm", fake)
        scenes = [
            _make_scene("i2v", init_image=str(img1), category="photo"),
            _make_scene("i2v", init_image=str(img2), category="photo"),
        ]
        VideoPromptEngine().generate_batch(scenes, "daily")

        brief_calls = [c for c in calls if c.get("call_type") == "video_image_brief"]
        assert len(brief_calls) == 1, "두 번째 씬은 vision 비활성 플래그로 생략돼야 함"
        # 두 씬 모두 카테고리 힌트 경로로 프롬프트는 생성됨
        assert all(s.video_prompt for s in scenes)

    def test_prev_shot_tracked_across_t2v_scenes(self, monkeypatch):
        """첫 T2V 씬의 프레이밍이 다음 씬 프롬프트에 전달된다."""
        from ai_worker.video.prompt_engine import VideoPromptEngine
        monkeypatch.setattr(
            "ai_worker.video.prompt_engine.llm_backend_supports_vision", lambda: False,
        )
        calls = _patch_llm(monkeypatch, [_VALID_T2V])  # 모든 호출 동일 응답
        scenes = [_make_scene("t2v"), _make_scene("t2v")]
        VideoPromptEngine().generate_batch(scenes, "daily")
        t2v_calls = [c for c in calls if c.get("call_type") == "video_prompt_t2v"]
        assert len(t2v_calls) == 2
        assert "Previous clip framing" not in t2v_calls[0]["prompt"]
        assert "Previous clip framing: medium shot" in t2v_calls[1]["prompt"]


# ──────────────────────────────────────────────
# transport vision 입력 (mock)
# ──────────────────────────────────────────────

class _FakeResp:
    status_code = 200

    def json(self) -> dict:
        return {"content": [{"type": "text", "text": "ok"}], "usage": {}}

    def raise_for_status(self) -> None:
        pass


class TestTransportVision:

    def test_encode_image_blocks_format(self, tmp_path):
        from ai_worker.llm.transport import _encode_image_blocks
        img = tmp_path / "pic.png"
        img.write_bytes(b"\x89PNG-fake")
        blocks = _encode_image_blocks([img])
        assert len(blocks) == 1
        assert blocks[0]["type"] == "image"
        assert blocks[0]["source"]["type"] == "base64"
        assert blocks[0]["source"]["media_type"] == "image/png"
        assert len(blocks[0]["source"]["data"]) > 0

    def test_encode_skips_missing_and_unsupported(self, tmp_path):
        from ai_worker.llm.transport import _encode_image_blocks
        missing = tmp_path / "none.jpg"
        bad_ext = tmp_path / "doc.txt"
        bad_ext.write_text("not an image")
        assert _encode_image_blocks([missing, bad_ext]) == []

    def test_encode_skips_oversized(self, tmp_path, monkeypatch):
        import ai_worker.llm.transport as tp
        monkeypatch.setattr(tp, "_IMAGE_MAX_BYTES", 4)
        img = tmp_path / "big.jpg"
        img.write_bytes(b"12345")
        assert tp._encode_image_blocks([img]) == []

    def test_api_body_contains_image_then_text(self, tmp_path, monkeypatch):
        """api 백엔드에서 messages[0].content가 [이미지, 텍스트] 순서로 구성된다."""
        import ai_worker.llm.transport as tp
        img = tmp_path / "pic.jpg"
        img.write_bytes(b"jpg-bytes")
        captured: dict = {}

        def fake_post(url, json=None, headers=None, timeout=None):
            captured["body"] = json
            return _FakeResp()

        monkeypatch.setattr(tp, "_get_anthropic_api_key", lambda: "test-key")
        monkeypatch.setattr(tp, "_get_api_base_url", lambda: "https://api.anthropic.com/v1")
        monkeypatch.setattr(tp._session, "post", fake_post)

        result = tp._call_via_api(
            "describe this",
            resolved_model="claude-haiku-4-5-20251001",
            max_tokens=100, temperature=0.2, json_mode=False, timeout=30,
            images=[img],
        )
        assert result == "ok"
        content = captured["body"]["messages"][0]["content"]
        assert isinstance(content, list)
        assert content[0]["type"] == "image"
        assert content[0]["source"]["media_type"] == "image/jpeg"
        assert content[1] == {"type": "text", "text": "describe this"}

    def test_api_body_plain_string_without_images(self, monkeypatch):
        import ai_worker.llm.transport as tp
        captured: dict = {}

        def fake_post(url, json=None, headers=None, timeout=None):
            captured["body"] = json
            return _FakeResp()

        monkeypatch.setattr(tp, "_get_anthropic_api_key", lambda: "test-key")
        monkeypatch.setattr(tp, "_get_api_base_url", lambda: "https://api.anthropic.com/v1")
        monkeypatch.setattr(tp._session, "post", fake_post)

        tp._call_via_api(
            "hello",
            resolved_model="claude-haiku-4-5-20251001",
            max_tokens=100, temperature=0.2, json_mode=False, timeout=30,
        )
        assert captured["body"]["messages"][0]["content"] == "hello"

    def test_cli_backend_ignores_images(self, tmp_path, monkeypatch, caplog):
        """cli 백엔드는 이미지를 무시(경고)하고 텍스트만 전송한다."""
        import ai_worker.llm.transport as tp
        img = tmp_path / "pic.jpg"
        img.write_bytes(b"jpg")
        captured: dict = {}

        def fake_post(url, json=None, timeout=None, **kwargs):
            captured["payload"] = json
            class R:
                def raise_for_status(self):
                    pass
                def json(self):
                    return {"text": "ok"}
            return R()

        monkeypatch.setattr(tp, "_get_llm_backend", lambda: "cli")
        monkeypatch.setattr(tp, "_get_worker_url", lambda: "http://fake:8090")
        monkeypatch.setattr(tp._session, "post", fake_post)

        with caplog.at_level(logging.WARNING):
            result = tp.call_llm("hello", call_type="raw", images=[img])
        assert result == "ok"
        assert captured["payload"]["prompt"] == "hello"
        assert any("vision 미지원" in r.message for r in caplog.records)

    def test_vision_support_flag(self, monkeypatch):
        import ai_worker.llm.transport as tp
        monkeypatch.setattr(tp, "_get_llm_backend", lambda: "api")
        assert tp.llm_backend_supports_vision() is True
        monkeypatch.setattr(tp, "_get_llm_backend", lambda: "cli")
        assert tp.llm_backend_supports_vision() is False


# ──────────────────────────────────────────────
# video_styles.json / NEGATIVE_PROMPT 계약
# ──────────────────────────────────────────────

class TestStaticAssets:

    def test_video_styles_json_loaded(self):
        """config/video_styles.json이 정상 로드되고 9개 mood × 4키를 포함한다."""
        from ai_worker.video.prompt_engine import _load_video_styles
        styles = _load_video_styles()
        expected_moods = {"humor", "touching", "anger", "sadness", "horror",
                          "info", "controversy", "daily", "shock"}
        assert expected_moods.issubset(set(styles.keys())), \
            f"누락된 mood: {expected_moods - set(styles.keys())}"
        for mood, data in styles.items():
            for key in ("style_hint", "camera_hints", "color_palette", "atmosphere"):
                assert key in data, f"{mood}에 {key} 없음"

    def test_video_styles_no_anti_realism_cues(self):
        """편집 효과/반실사 단서가 스타일에 남아있지 않다 (LTX-2 실사 원칙)."""
        from ai_worker.video.prompt_engine import _load_video_styles
        banned = ("fish-eye", "pop-art", "glitch", "freeze frame", "freeze-frame",
                  "speed ramp", "split-screen", "strobing", "whip pan",
                  "crash zoom", "snap zoom")
        styles = _load_video_styles()
        for mood, data in styles.items():
            blob = str(data).lower()
            for cue in banned:
                assert cue not in blob, f"{mood}에 반실사 단서 잔존: {cue}"

    def test_negative_prompt_v2_content(self):
        """네거티브 프롬프트가 한국 중심 필터링을 포함한다 (full 모드용)."""
        from ai_worker.video.prompt_engine import NEGATIVE_PROMPT
        assert "western faces" in NEGATIVE_PROMPT
        assert "cyberpunk" in NEGATIVE_PROMPT
        assert "anime" in NEGATIVE_PROMPT


# ──────────────────────────────────────────────
# 실 LLM 스모크 (게이트)
# ──────────────────────────────────────────────

class TestVideoPromptEngineLive:

    @requires_llm
    def test_generate_prompt_humor(self):
        """humor 무드로 프롬프트를 생성하면 검증 통과한 영어 문단이 반환된다."""
        from ai_worker.video.prompt_engine import VideoPromptEngine, _validate_prompt
        engine = VideoPromptEngine()
        prompt = engine.generate_prompt(
            text_lines=["오늘 회사에서 웃긴 일이 있었는데"],
            mood="humor",
            title="직장 웃긴 썰",
            duration_sec=5.0,
        )
        assert len(prompt) > 50, "프롬프트가 너무 짧음"
        ok, reason = _validate_prompt(prompt)
        assert ok, f"검증 실패: {reason}"

        with open(OUTPUT_DIR / "generated_prompts.txt", "a", encoding="utf-8") as f:
            f.write(f"=== humor (V3) ===\n{prompt}\n\n")

    @requires_llm
    def test_generate_prompt_horror(self):
        """horror 무드로 프롬프트를 생성한다."""
        from ai_worker.video.prompt_engine import VideoPromptEngine
        engine = VideoPromptEngine()
        prompt = engine.generate_prompt(
            text_lines=["밤에 혼자 집에 있는데 이상한 소리가 들렸다"],
            mood="horror",
            title="심야 공포 체험",
        )
        assert len(prompt) > 50

        with open(OUTPUT_DIR / "generated_prompts.txt", "a", encoding="utf-8") as f:
            f.write(f"=== horror (V3) ===\n{prompt}\n\n")

    @requires_llm
    def test_simplify_prompt(self):
        """simplify_prompt가 원본보다 짧은 프롬프트를 반환한다."""
        from ai_worker.video.prompt_engine import VideoPromptEngine
        engine = VideoPromptEngine()
        original = (
            "A handsome Korean man in his early thirties stands in a modern Seoul office, "
            "looking at documents on his desk with a focused expression. He wears a navy blue suit "
            "with a loosened tie. Fluorescent office lighting mixed with natural light from floor-to-ceiling "
            "windows showing the Gangnam skyline. He picks up his phone and checks it briefly. "
            "Camera at eye level, medium shot from waist up. Sound of keyboard typing and distant phone ringing."
        )
        simplified = engine.simplify_prompt(original)
        assert len(simplified) < len(original), "단순화 프롬프트가 원본보다 길면 안 됨"

    @requires_llm
    def test_all_9_moods(self):
        """9가지 mood 전체에 대해 검증 통과 프롬프트를 생성한다."""
        from ai_worker.video.prompt_engine import VideoPromptEngine, _validate_prompt
        engine = VideoPromptEngine()
        moods = ["humor", "touching", "anger", "sadness", "horror",
                 "info", "controversy", "daily", "shock"]

        results = {}
        for mood in moods:
            prompt = engine.generate_prompt(
                text_lines=["테스트 텍스트입니다"],
                mood=mood,
                title="테스트 제목",
            )
            results[mood] = prompt
            assert len(prompt) > 30, f"{mood} 프롬프트 생성 실패"
            ok, reason = _validate_prompt(prompt)
            assert ok, f"{mood} 검증 실패: {reason}"

        with open(OUTPUT_DIR / "all_moods_prompts.txt", "w", encoding="utf-8") as f:
            for mood, prompt in results.items():
                f.write(f"=== {mood} ===\n{prompt}\n\n")

    @requires_llm
    def test_visual_anchor_live(self):
        """비주얼 앵커가 영어 2~3문장으로 생성된다."""
        from ai_worker.video.prompt_engine import VideoPromptEngine, _validate_prompt
        engine = VideoPromptEngine()
        anchor = engine.generate_visual_anchor(
            title="시어머니가 한 말 때문에 이혼 결심했어요",
            body_summary="결혼 3년차 며느리가 명절에 시댁에서 겪은 갈등과 "
                         "남편의 무관심, 그리고 마지막에 들은 충격적인 말.",
            mood="anger",
        )
        # 실패 시 빈 문자열 허용 (파이프라인 비중단 계약) — 생성됐다면 검증 통과해야 함
        if anchor:
            ok, reason = _validate_prompt(anchor)
            assert ok, f"앵커 검증 실패: {reason}"
            with open(OUTPUT_DIR / "visual_anchor.txt", "w", encoding="utf-8") as f:
                f.write(anchor + "\n")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
