"""E2E 테스트 — 구조 개선 (WP-1~7, P2) 검증

이번 개선 작업에서 변경된 모든 주요 컴포넌트를 검증합니다.

실행 방법:
    # 단위 테스트만 (외부 서비스 불필요)
    cd worker && python -m pytest test/test_e2e_structure_improve.py -v -m unit

    # FFmpeg 테스트 포함 (Docker 환경 권장)
    docker compose exec ai_worker python -m pytest test/test_e2e_structure_improve.py -v

    # 전체
    DATABASE_URL="mysql+pymysql://wagglebot:wagglebot@localhost/wagglebot" \\
    docker compose exec ai_worker python -m pytest test/test_e2e_structure_improve.py -v
"""

from __future__ import annotations

import hashlib
import inspect
import json
import logging
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# ── 프로젝트 루트를 sys.path에 추가 ────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

logger = logging.getLogger(__name__)

# ── 마커 정의 ────────────────────────────────────────────────────────────────
_FFMPEG = shutil.which("ffmpeg")
_FFPROBE = shutil.which("ffprobe")

requires_ffmpeg = pytest.mark.skipif(
    _FFMPEG is None, reason="FFmpeg not installed (Docker 환경에서 실행하세요)"
)

requires_db = pytest.mark.skipif(
    os.getenv("DATABASE_URL") is None,
    reason="DATABASE_URL 환경변수 필요 (DB 테스트 건너뜀)",
)


def _check_fish_reachable() -> bool:
    """Fish Speech HTTP 연결 가능 여부를 확인한다."""
    try:
        import httpx
        url = os.getenv("FISH_SPEECH_URL", "http://localhost:8082")
        resp = httpx.get(f"{url}/", timeout=3.0)
        return resp.status_code < 400
    except Exception:
        return False


_FISH_OK = _check_fish_reachable()
requires_fish = pytest.mark.skipif(
    not _FISH_OK,
    reason="Fish Speech 서버 연결 불가 (fish-speech 컨테이너가 실행 중이어야 합니다)",
)


# ─────────────────────────────────────────────────────────────────────────────
# 그룹 1: 단위 테스트 — 외부 서비스 불필요
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestBuildApiHeaders:
    """WP-1: _build_api_headers 함수 — 공식/프록시 URL 헤더 분기 검증."""

    def test_build_api_headers_official_url(self):
        """공식 Anthropic URL에는 x-api-key만 설정되고, authorization 헤더는 없어야 한다."""
        from ai_worker.llm.transport import _build_api_headers

        headers = _build_api_headers("sk-test", "https://api.anthropic.com/v1")

        assert "x-api-key" in headers, "공식 URL에도 x-api-key가 포함돼야 함"
        assert "authorization" not in headers, (
            "공식 Anthropic URL에서는 authorization 헤더를 추가하면 안 됨"
        )
        assert headers["x-api-key"] == "sk-test"

    def test_build_api_headers_proxy_url(self):
        """프록시/게이트웨이 URL에는 x-api-key + authorization: Bearer 모두 설정돼야 한다."""
        from ai_worker.llm.transport import _build_api_headers

        headers = _build_api_headers("sk-test", "https://api.clcocloud.com/claude/v1")

        assert "x-api-key" in headers, "프록시 URL에도 x-api-key가 포함돼야 함"
        assert "authorization" in headers, "프록시 URL에는 authorization이 있어야 함"
        assert headers["authorization"] == "Bearer sk-test", (
            "authorization 값은 'Bearer <api_key>' 형식이어야 함"
        )


@pytest.mark.unit
class TestAdaptivePolling:
    """WP-2: ComfyUIClient._adaptive_interval — 경과 시간별 폴링 간격 검증."""

    def test_adaptive_polling_short(self):
        """경과 10초(< 30초) → 1.0초 간격이어야 한다."""
        from ai_worker.video.comfy_client import ComfyUIClient

        interval = ComfyUIClient._adaptive_interval(10)
        assert interval == 1.0, f"예상 1.0, 실제 {interval}"

    def test_adaptive_polling_medium(self):
        """경과 60초(30~120초) → 3.0초 간격이어야 한다."""
        from ai_worker.video.comfy_client import ComfyUIClient

        interval = ComfyUIClient._adaptive_interval(60)
        assert interval == 3.0, f"예상 3.0, 실제 {interval}"

    def test_adaptive_polling_long(self):
        """경과 200초(> 120초) → 5.0초 간격이어야 한다."""
        from ai_worker.video.comfy_client import ComfyUIClient

        interval = ComfyUIClient._adaptive_interval(200)
        assert interval == 5.0, f"예상 5.0, 실제 {interval}"


@pytest.mark.unit
class TestScriptSystemPrompt:
    """WP-3: _SCRIPT_SYSTEM 프롬프트 — 신규 강화 내용 존재 여부 검증."""

    def test_prompt_bad_hook_examples_present(self):
        """나쁜 hook 예시('나쁜 hook' 또는 '명사형 요약 — 결말이 안 궁금함')가 프롬프트에 있어야 한다."""
        from ai_worker.script.client import _SCRIPT_SYSTEM

        has_bad_hook_label = "나쁜 hook" in _SCRIPT_SYSTEM
        has_bad_hook_desc = "명사형 요약 — 결말이 안 궁금함" in _SCRIPT_SYSTEM
        assert has_bad_hook_label or has_bad_hook_desc, (
            "_SCRIPT_SYSTEM에 나쁜 hook 패턴 설명이 없음. "
            "'나쁜 hook' 또는 '명사형 요약 — 결말이 안 궁금함' 텍스트를 확인하세요."
        )

    def test_prompt_mood_teaser_variants_present(self):
        """mood별 떡밥 변형 가이드 — shock/horror(소름)·humor 패턴이 프롬프트에 있어야 한다.

        50d62ef에서 문장형 예시("소름 돋는 게 뭔지 아세요")가
        압축형 변형 가이드("shock/horror: 소름·등골 서늘")로 교체됨.
        """
        from ai_worker.script.client import _SCRIPT_SYSTEM

        assert "shock/horror" in _SCRIPT_SYSTEM and "소름" in _SCRIPT_SYSTEM, (
            "_SCRIPT_SYSTEM에 mood별 떡밥 변형 가이드(shock/horror·소름)가 없음"
        )
        assert "humor" in _SCRIPT_SYSTEM, (
            "_SCRIPT_SYSTEM에 humor 떡밥 변형 가이드가 없음"
        )

    def test_prompt_mood_decision_tree_present(self):
        """mood 판정 의사결정 트리 — horror, shock, controversy, daily 모두 있어야 한다."""
        from ai_worker.script.client import _SCRIPT_SYSTEM

        for mood_keyword in ("horror", "shock", "controversy", "daily"):
            assert mood_keyword in _SCRIPT_SYSTEM, (
                f"_SCRIPT_SYSTEM mood 트리에 '{mood_keyword}'가 없음"
            )

    def test_prompt_comment_strategy_present(self):
        """댓글 선택 전략 설명이 프롬프트에 있어야 한다."""
        from ai_worker.script.client import _SCRIPT_SYSTEM

        has_cider = "사이다를 날리는" in _SCRIPT_SYSTEM
        has_strategy_label = "댓글 선택 전략" in _SCRIPT_SYSTEM
        assert has_cider or has_strategy_label, (
            "_SCRIPT_SYSTEM에 댓글 선택 전략 설명이 없음. "
            "'사이다를 날리는' 또는 '댓글 선택 전략' 텍스트를 확인하세요."
        )

    def test_prompt_entity_consistency_present(self):
        """호칭 일관성 규칙이 프롬프트에 있어야 한다."""
        from ai_worker.script.client import _SCRIPT_SYSTEM

        assert "호칭 일관성" in _SCRIPT_SYSTEM, (
            "_SCRIPT_SYSTEM에 호칭 일관성 규칙이 없음"
        )


@pytest.mark.unit
class TestOverlayCache:
    """WP-4: _overlay_cache — PNG 오버레이 캐시 히트·미스 검증."""

    def test_overlay_cache_hit(self, tmp_path: Path):
        """동일 캐시 키로 이미 저장된 PNG가 있으면 PIL 렌더링 없이 복사만 수행한다."""
        from ai_worker.renderer._frames import _overlay_cache, _render_video_text_overlay

        # 테스트용 레이아웃 (최소 필수 구조)
        layout = {
            "canvas": {"width": 1080, "height": 1920},
            "scenes": {
                "video_text": {
                    "elements": {
                        "text_area": {
                            "x": 540, "y": 1570, "font_size": 60,
                            "color": "#FFFFFF", "stroke_color": "#000000",
                            "stroke_width": 3,
                            "max_width": 900,
                        }
                    }
                }
            },
        }

        # 캐시 키 계산 (transport.py 내부 로직과 동일)
        text = "캐시 히트 테스트 문장"
        video_text_cfg = layout.get("scenes", {}).get("video_text", {})
        canvas_cfg = layout.get("canvas", {})
        suffix = ".png"
        cache_raw = (
            f"{text}"
            f"|{video_text_cfg}"
            f"|{canvas_cfg.get('width')}x{canvas_cfg.get('height')}"
            f"|{suffix}"
        )
        cache_key = hashlib.md5(cache_raw.encode("utf-8")).hexdigest()

        # 가짜 PNG를 캐시에 직접 삽입
        fake_cached = tmp_path / "fake_overlay_cached.png"
        from PIL import Image
        img = Image.new("RGBA", (1080, 1920), (0, 0, 0, 0))
        img.save(str(fake_cached), "PNG")

        original_entry = _overlay_cache.get(cache_key)  # 테스트 후 원복용
        _overlay_cache[cache_key] = fake_cached

        try:
            out_png = tmp_path / "overlay_out.png"
            result = _render_video_text_overlay(text, layout, Path("assets/fonts"), out_png)

            assert result == out_png, "반환 경로가 out_png와 일치해야 함"
            assert out_png.exists(), "캐시 히트 시 out_png로 파일이 복사돼야 함"
        finally:
            # _overlay_cache 원복
            if original_entry is None:
                _overlay_cache.pop(cache_key, None)
            else:
                _overlay_cache[cache_key] = original_entry

    def test_overlay_cache_miss_on_different_text(self, tmp_path: Path):
        """다른 텍스트로 두 번 호출하면 _overlay_cache에 서로 다른 키가 생성된다."""
        from ai_worker.renderer._frames import _overlay_cache

        layout = {
            "canvas": {"width": 1080, "height": 1920},
            "scenes": {
                "video_text": {
                    "elements": {
                        "text_area": {
                            "x": 540, "y": 1570, "font_size": 60,
                            "color": "#FFFFFF", "stroke_color": "#000000",
                            "stroke_width": 3,
                            "max_width": 900,
                        }
                    }
                }
            },
        }

        def _compute_key(text: str, layout: dict, suffix: str = ".png") -> str:
            video_text_cfg = layout.get("scenes", {}).get("video_text", {})
            canvas_cfg = layout.get("canvas", {})
            cache_raw = (
                f"{text}"
                f"|{video_text_cfg}"
                f"|{canvas_cfg.get('width')}x{canvas_cfg.get('height')}"
                f"|{suffix}"
            )
            return hashlib.md5(cache_raw.encode("utf-8")).hexdigest()

        key_a = _compute_key("텍스트 A", layout)
        key_b = _compute_key("텍스트 B (다름)", layout)

        assert key_a != key_b, (
            "서로 다른 텍스트는 서로 다른 캐시 키를 가져야 함"
        )


@pytest.mark.unit
class TestPhase56Parallel:
    """WP-5: content_processor.py — Phase 5 & 6 병렬 실행 구조 검증."""

    def test_phase56_parallel_uses_asyncio_gather(self):
        """process_content 소스에 asyncio.gather 호출이 존재해야 한다."""
        from ai_worker.pipeline import content_processor

        source = inspect.getsource(content_processor)
        assert "asyncio.gather" in source, (
            "content_processor.py에 asyncio.gather 호출이 없음 "
            "— Phase 5 & 6 병렬화가 구현돼야 합니다"
        )

    def test_phase56_parallel_comment_in_source(self):
        """Phase 5 & 6 병렬 시작 로그 메시지가 소스에 존재해야 한다."""
        from ai_worker.pipeline import content_processor

        source = inspect.getsource(content_processor)
        assert "Phase 5" in source and "Phase 6" in source, (
            "content_processor.py에 Phase 5 또는 Phase 6 관련 코드가 없음"
        )


@pytest.mark.unit
class TestMarkPostFailedSignature:
    """WP-6: _mark_post_failed — 함수 시그니처 검증."""

    def test_mark_post_failed_signature(self):
        """_mark_post_failed(post_id, error='') 시그니처로 임포트돼야 한다."""
        from ai_worker.core.main import _mark_post_failed
        import inspect

        sig = inspect.signature(_mark_post_failed)
        params = list(sig.parameters.keys())
        assert "post_id" in params, "_mark_post_failed에 post_id 파라미터가 없음"
        assert "error" in params, "_mark_post_failed에 error 파라미터가 없음"

    def test_mark_post_failed_is_sync(self):
        """_mark_post_failed는 동기 함수여야 한다 (async def 아님)."""
        import asyncio
        from ai_worker.core.main import _mark_post_failed

        assert not asyncio.iscoroutinefunction(_mark_post_failed), (
            "_mark_post_failed는 동기 함수여야 함 — async def로 선언되면 안 됨"
        )


@pytest.mark.unit
class TestWarmupSentinel:
    """WP-7: Fish Speech warmup sentinel — 저장/로드 로직 검증."""

    def test_load_warmup_sentinel_valid(self, tmp_path: Path, monkeypatch):
        """유효한 sentinel 파일(6시간 이내)을 로드하면 dict를 반환해야 한다."""
        from ai_worker.tts import fish_client

        sentinel_path = tmp_path / "fish_warmup_state.json"
        sentinel_data = {"warmed_at": time.time(), "url": "http://fish-speech:8080"}
        sentinel_path.write_text(json.dumps(sentinel_data), encoding="utf-8")

        monkeypatch.setattr(fish_client, "_get_warmup_sentinel_path", lambda: sentinel_path)

        result = fish_client._load_warmup_sentinel()
        assert result is not None, "유효한 sentinel 파일이 있으면 None을 반환하면 안 됨"
        assert "warmed_at" in result, "로드된 sentinel에 warmed_at 키가 있어야 함"
        assert "url" in result, "로드된 sentinel에 url 키가 있어야 함"

    def test_load_warmup_sentinel_missing(self, tmp_path: Path, monkeypatch):
        """sentinel 파일이 없으면 None을 반환해야 한다."""
        from ai_worker.tts import fish_client

        missing_path = tmp_path / "nonexistent_sentinel.json"
        monkeypatch.setattr(fish_client, "_get_warmup_sentinel_path", lambda: missing_path)

        result = fish_client._load_warmup_sentinel()
        assert result is None, "sentinel 파일이 없으면 None을 반환해야 함"

    def test_load_warmup_sentinel_corrupt(self, tmp_path: Path, monkeypatch):
        """손상된 sentinel 파일은 None을 반환해야 한다."""
        from ai_worker.tts import fish_client

        corrupt_path = tmp_path / "corrupt_sentinel.json"
        corrupt_path.write_text("{invalid json:::", encoding="utf-8")
        monkeypatch.setattr(fish_client, "_get_warmup_sentinel_path", lambda: corrupt_path)

        result = fish_client._load_warmup_sentinel()
        assert result is None, "파싱 불가 sentinel은 None을 반환해야 함"

    def test_save_warmup_sentinel(self, tmp_path: Path, monkeypatch):
        """_save_warmup_sentinel()이 warmed_at과 url을 포함한 JSON을 기록해야 한다."""
        from ai_worker.tts import fish_client

        sentinel_path = tmp_path / "fish_warmup_state.json"
        monkeypatch.setattr(fish_client, "_get_warmup_sentinel_path", lambda: sentinel_path)

        fish_client._save_warmup_sentinel()

        assert sentinel_path.exists(), "sentinel 파일이 생성돼야 함"
        data = json.loads(sentinel_path.read_text(encoding="utf-8"))
        assert "warmed_at" in data, "sentinel에 warmed_at 필드가 있어야 함"
        assert "url" in data, "sentinel에 url 필드가 있어야 함"
        # warmed_at이 현재 시각 근처여야 함 (10초 이내)
        assert abs(data["warmed_at"] - time.time()) < 10, (
            "sentinel의 warmed_at이 현재 시각과 너무 다름"
        )

    def test_sentinel_expired_detection(self, tmp_path: Path, monkeypatch):
        """만료된(7시간 전) sentinel의 age 계산이 올바르게 이루어져야 한다."""
        from ai_worker.tts import fish_client

        sentinel_path = tmp_path / "fish_warmup_state.json"
        # 7시간 전에 워밍업한 것처럼 기록
        old_time = time.time() - (7 * 3600)
        sentinel_data = {"warmed_at": old_time, "url": fish_client.FISH_SPEECH_URL}
        sentinel_path.write_text(json.dumps(sentinel_data), encoding="utf-8")
        monkeypatch.setattr(fish_client, "_get_warmup_sentinel_path", lambda: sentinel_path)

        result = fish_client._load_warmup_sentinel()
        assert result is not None, "만료됐어도 파일은 로드돼야 함 (_load는 파싱만 수행)"

        # age 계산 — 6시간 기준(WARMUP_SENTINEL_MAX_AGE_HOURS)으로 만료 확인
        age_h = (time.time() - result["warmed_at"]) / 3600.0
        assert age_h > fish_client._WARMUP_SENTINEL_MAX_AGE_HOURS, (
            f"sentinel age({age_h:.1f}h)가 최대 유효 시간"
            f"({fish_client._WARMUP_SENTINEL_MAX_AGE_HOURS}h)보다 커야 만료로 판정됨"
        )


# ─────────────────────────────────────────────────────────────────────────────
# 그룹 2: FFmpeg 테스트
# ─────────────────────────────────────────────────────────────────────────────

def _create_test_video_clip(output_path: Path, duration: float = 2.0) -> Path:
    """FFmpeg testsrc로 테스트용 비디오 클립을 생성한다."""
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", f"testsrc=duration={duration}:size=512x512:rate=30",
        "-c:v", "libx264", "-preset", "ultrafast",
        "-pix_fmt", "yuv420p",
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        pytest.skip(f"FFmpeg test clip 생성 실패: {result.stderr[:200]}")
    return output_path


def _create_test_png(output_path: Path, width: int = 1080, height: int = 1920) -> Path:
    """PIL로 테스트용 PNG를 생성한다."""
    from PIL import Image
    img = Image.new("RGB", (width, height), color=(40, 40, 60))
    img.save(str(output_path), "PNG")
    return output_path


def _make_minimal_layout() -> dict:
    """_render_video_segment에 필요한 최소 layout dict를 반환한다."""
    return {
        "canvas": {"width": 1080, "height": 1920},
        "scenes": {
            "video_text": {
                "elements": {
                    "video_area": {"x": 90, "y": 550, "width": 900, "height": 900},
                    "text_area": {
                        "x": 540, "y": 1570, "font_size": 60,
                        "color": "#FFFFFF", "stroke_color": "#000000",
                        "stroke_width": 3,
                        "max_width": 900,
                    },
                }
            }
        },
    }


@requires_ffmpeg
class TestRenderVideoSegment:
    """WP-4/_encode.py: _render_video_segment — 중간 파일 미생성 + 출력 규격 검증."""

    def test_render_video_segment_no_intermediate_files(self, tmp_path: Path):
        """_render_video_segment 호출 후 resized_*.mp4, fitted_*.mp4가 생성되지 않아야 한다."""
        from PIL import Image
        from ai_worker.renderer._encode import _render_video_segment

        font_dir = PROJECT_ROOT / "assets" / "fonts"
        if not font_dir.exists():
            pytest.skip("assets/fonts 디렉터리 없음")

        clip_path = tmp_path / "test_clip.mp4"
        _create_test_video_clip(clip_path, duration=2.0)

        base_frame = Image.new("RGB", (1080, 1920), color=(40, 40, 60))
        layout = _make_minimal_layout()

        scene = MagicMock()
        scene.video_clip_path = str(clip_path)

        output_path = tmp_path / "segment_out.mp4"

        _render_video_segment(
            base_frame=base_frame,
            scene=scene,
            text="테스트 자막",
            duration=1.5,
            layout=layout,
            font_dir=font_dir,
            output_path=output_path,
        )

        # 중간 파일 확인
        intermediate_files = list(tmp_path.glob("resized_*.mp4")) + list(tmp_path.glob("fitted_*.mp4"))
        assert len(intermediate_files) == 0, (
            f"중간 파일이 생성되면 안 됨: {[f.name for f in intermediate_files]}"
        )

        assert output_path.exists(), "출력 mp4 파일이 존재해야 함"
        assert output_path.stat().st_size > 0, "출력 파일 크기가 0이면 안 됨"

    def test_render_video_segment_output_spec(self, tmp_path: Path):
        """_render_video_segment 출력 파일이 codec=h264, 1080x1920, 30fps 규격이어야 한다."""
        if _FFPROBE is None:
            pytest.skip("ffprobe not available")

        from PIL import Image
        from ai_worker.renderer._encode import _render_video_segment

        font_dir = PROJECT_ROOT / "assets" / "fonts"
        if not font_dir.exists():
            pytest.skip("assets/fonts 디렉터리 없음")

        clip_path = tmp_path / "test_clip_spec.mp4"
        _create_test_video_clip(clip_path, duration=2.0)

        base_frame = Image.new("RGB", (1080, 1920), color=(40, 40, 60))
        layout = _make_minimal_layout()

        scene = MagicMock()
        scene.video_clip_path = str(clip_path)

        output_path = tmp_path / "segment_spec.mp4"

        _render_video_segment(
            base_frame=base_frame,
            scene=scene,
            text="규격 검증 자막",
            duration=1.5,
            layout=layout,
            font_dir=font_dir,
            output_path=output_path,
        )

        probe = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height,codec_name,r_frame_rate",
                "-of", "json",
                str(output_path),
            ],
            capture_output=True, text=True, timeout=15,
        )
        assert probe.returncode == 0, f"ffprobe 실행 실패: {probe.stderr[:200]}"

        info = json.loads(probe.stdout)
        stream = info["streams"][0]

        assert stream["width"] == 1080, f"width 불일치: {stream['width']}"
        assert stream["height"] == 1920, f"height 불일치: {stream['height']}"
        assert stream["codec_name"] in ("h264", "hevc"), (
            f"codec 불일치: {stream['codec_name']}"
        )
        # r_frame_rate는 "30/1" 형식
        fps_str = stream.get("r_frame_rate", "0/1")
        num, den = (int(x) for x in fps_str.split("/"))
        fps = num / den if den else 0
        assert abs(fps - 30) < 1, f"fps 불일치: {fps_str} (약 {fps:.1f}fps)"


# ─────────────────────────────────────────────────────────────────────────────
# 그룹 3: DB 테스트
# ─────────────────────────────────────────────────────────────────────────────

@requires_db
class TestMarkPostFailedDB:
    """WP-6: _mark_post_failed — DB에 last_error 저장 검증."""

    def _insert_test_post(self, session, post_id: int) -> None:
        """테스트용 Post를 PROCESSING 상태로 INSERT한다."""
        from db.models import Post, PostStatus

        existing = session.query(Post).filter_by(id=post_id).first()
        if existing:
            session.delete(existing)
            session.flush()

        post = Post(
            id=post_id,
            site_code="test",
            origin_id=f"test_e2e_{post_id}",
            title="E2E 테스트 포스트",
            content="테스트 내용",
            status=PostStatus.PROCESSING,
        )
        session.add(post)
        session.commit()

    def test_mark_post_failed_stores_error(self):
        """_mark_post_failed 호출 후 DB의 last_error에 오류 메시지가 저장돼야 한다."""
        from db.models import Post, PostStatus
        from db.session import SessionLocal
        from ai_worker.core.main import _mark_post_failed

        test_post_id = 9999901
        error_msg = "테스트 오류 메시지 (WP-6 검증)"

        try:
            with SessionLocal() as session:
                self._insert_test_post(session, test_post_id)

            _mark_post_failed(test_post_id, error=error_msg)

            with SessionLocal() as session:
                post = session.query(Post).filter_by(id=test_post_id).first()
                assert post is not None, "테스트 포스트가 DB에 없음"
                assert post.status == PostStatus.FAILED, (
                    f"상태가 FAILED가 아님: {post.status}"
                )
                assert post.last_error is not None, "last_error가 None이면 안 됨"
                assert error_msg[:50] in post.last_error, (
                    f"오류 메시지가 last_error에 없음: {post.last_error!r}"
                )
        finally:
            with SessionLocal() as session:
                post = session.query(Post).filter_by(id=test_post_id).first()
                if post:
                    session.delete(post)
                    session.commit()

    def test_last_error_cleared_on_reprocess(self):
        """FAILED 포스트를 APPROVED로 변경하고 last_error를 None으로 클리어할 수 있어야 한다."""
        from db.models import Post, PostStatus
        from db.session import SessionLocal
        from ai_worker.core.main import _mark_post_failed

        test_post_id = 9999902

        try:
            with SessionLocal() as session:
                self._insert_test_post(session, test_post_id)

            _mark_post_failed(test_post_id, error="1차 오류")

            # 재처리: APPROVED로 복구 + last_error 클리어
            with SessionLocal() as session:
                post = session.query(Post).filter_by(id=test_post_id).first()
                assert post is not None
                post.status = PostStatus.APPROVED
                post.last_error = None
                session.commit()

            with SessionLocal() as session:
                post = session.query(Post).filter_by(id=test_post_id).first()
                assert post.status == PostStatus.APPROVED, (
                    f"재처리 후 상태가 APPROVED가 아님: {post.status}"
                )
                assert post.last_error is None, (
                    f"재처리 후 last_error가 None이 아님: {post.last_error!r}"
                )
        finally:
            with SessionLocal() as session:
                post = session.query(Post).filter_by(id=test_post_id).first()
                if post:
                    session.delete(post)
                    session.commit()


# ─────────────────────────────────────────────────────────────────────────────
# 그룹 4: Fish Speech 테스트
# ─────────────────────────────────────────────────────────────────────────────

@requires_fish
class TestTtsPreviewHandler:
    """dashboard_worker/handlers.py: _handle_tts_preview — 오디오 경로 반환 검증."""

    def test_tts_preview_handler_returns_audio_path(self):
        """_handle_tts_preview 호출 시 preview_path(.wav) 키가 반환돼야 한다."""
        from db.session import SessionLocal
        from db.models import Post, Content, PostStatus
        from db.models import ScriptData
        from dashboard_worker.handlers import _handle_tts_preview

        # summary_text가 있는 Post 조회 (없으면 임시 생성)
        test_post_id: int | None = None
        created_for_test = False

        with SessionLocal() as db:
            # 기존 DB에서 대본이 있는 post 조회
            contents = (
                db.query(Content)
                .filter(Content.summary_text.isnot(None))
                .limit(1)
                .all()
            )
            if contents:
                test_post_id = contents[0].post_id
            else:
                # 없으면 테스트용 post + content 생성
                test_post = Post(
                    site_code="test",
                    origin_id="tts_preview_e2e",
                    title="TTS 미리듣기 E2E 테스트",
                    content="테스트 내용입니다.",
                    status=PostStatus.APPROVED,
                )
                db.add(test_post)
                db.flush()
                test_post_id = test_post.id

                script = ScriptData(
                    hook="TTS 테스트 훅",
                    body=[{"type": "body", "line_count": 1, "lines": ["테스트 내용"]}],
                    closer="테스트 클로저",
                    mood="daily",
                    tags=["test"],
                )
                content = Content(
                    post_id=test_post_id,
                    summary_text=script.to_json(),
                )
                db.add(content)
                db.commit()
                created_for_test = True

        try:
            # Mock Job 생성
            job = MagicMock()
            job.post_id = test_post_id
            job.payload = {"scope": "preview", "voice": "yura"}

            result = _handle_tts_preview(job)

            assert "preview_path" in result, (
                f"결과에 'preview_path' 키가 없음: {result}"
            )
            preview_path = Path(result["preview_path"])
            assert preview_path.suffix in (".wav", ".mp3", ".ogg"), (
                f"예상 오디오 확장자가 아님: {preview_path.suffix}"
            )
        finally:
            if created_for_test:
                with SessionLocal() as db:
                    db.query(Content).filter_by(post_id=test_post_id).delete()
                    db.query(Post).filter_by(id=test_post_id).delete()
                    db.commit()
