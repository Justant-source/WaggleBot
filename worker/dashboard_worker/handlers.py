"""dashboard_worker 잡 핸들러 — 기존 Python 함수를 직접 호출."""
from __future__ import annotations

import logging
from pathlib import Path

from db.models import Job, JobType

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 핸들러 구현
# ---------------------------------------------------------------------------

def _handle_generate_script(job: Job) -> dict:
    payload = job.payload or {}
    post_id = job.post_id
    model = payload.get("model")
    extra_instructions = payload.get("extra_instructions")
    call_type = payload.get("call_type", "generate_script_auto")

    from db.session import SessionLocal
    from db.models import Post, Content, Comment

    with SessionLocal() as db:
        post = db.query(Post).filter_by(id=post_id).first()
        if not post:
            raise ValueError(f"Post {post_id} not found")
        comments_raw = (
            db.query(Comment)
            .filter_by(post_id=post_id)
            .order_by(Comment.likes.desc())
            .limit(5)
            .all()
        )
        comments = [c.content for c in comments_raw]
        title = post.title
        body = post.content or ""

    from ai_worker.script.client import generate_script

    script = generate_script(
        title,
        body,
        comments,
        model=model,
        extra_instructions=extra_instructions,
        post_id=post_id,
        call_type=call_type,
    )

    with SessionLocal() as db:
        content = db.query(Content).filter_by(post_id=post_id).first()
        if content is None:
            from db.models import Content as ContentModel
            content = ContentModel(post_id=post_id)
            db.add(content)
        content.summary_text = script.to_json()
        db.commit()

    return {"script_json": script.to_json()}


def _handle_tts_preview(job: Job) -> dict:
    import asyncio
    from ai_worker.tts.fish_client import synthesize

    payload = job.payload or {}
    post_id = job.post_id
    scope = payload.get("scope", "preview")  # "preview" | "full"

    from db.session import SessionLocal
    from db.models import Content
    from config.settings import load_pipeline_config, MEDIA_DIR, TTS_OUTPUT_FORMAT

    cfg = load_pipeline_config()
    voice_key = payload.get("voice", cfg.get("tts_voice", "yura"))

    with SessionLocal() as db:
        content = db.query(Content).filter_by(post_id=post_id).first()
        if not content or not content.summary_text:
            raise ValueError("TTS 미리듣기: 대본 없음")
        from db.models import ScriptData
        script = ScriptData.from_json(content.summary_text)

    if scope == "full":
        # hook + 전체 body + closer 이어 붙이기
        lines = [script.hook]
        for item in script.body:
            if isinstance(item, dict):
                lines.extend(item.get("lines", []))
        closer = getattr(script, "closer", None)
        if closer:
            lines.append(closer)
    else:
        # 기본 preview: hook + body 앞 3개
        lines = [script.hook]
        for item in script.body[:3]:
            if isinstance(item, dict):
                lines.extend(item.get("lines", []))

    text = " ".join(lines)

    output_path = Path(MEDIA_DIR) / "tmp" / f"preview_{post_id}.{TTS_OUTPUT_FORMAT}"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    audio_path = asyncio.run(
        synthesize(text, voice_key=voice_key, output_path=output_path)
    )
    return {"preview_path": str(audio_path)}


def _handle_ai_fitness(job: Job) -> dict:
    post_id = job.post_id

    from db.session import SessionLocal
    from db.models import Post
    from ai_worker.llm.transport import call_llm_raw

    with SessionLocal() as db:
        post = db.query(Post).filter_by(id=post_id).first()
        if not post:
            raise ValueError(f"Post {post_id} not found")
        title = post.title
        body = (post.content or "")[:500]

    prompt = (
        f"다음 게시글이 유튜브 쇼츠 콘텐츠로 적합한지 분석하세요.\n"
        f"제목: {title}\n내용 앞부분: {body}\n\n"
        'JSON으로 응답: {"score": 0~100, "reason": "한 줄 이유", "recommended": true/false}'
    )
    raw = call_llm_raw(prompt, max_tokens=200)
    return {"raw": raw}


def _handle_manual_crawl(job: Job) -> dict:
    import crawlers  # noqa: F401 — 크롤러 자동 등록 (데코레이터)
    from crawlers.plugin_manager import CrawlerRegistry
    from config.settings import ENABLED_CRAWLERS
    from db.session import SessionLocal
    from db.models import Post

    enabled = [s.strip() for s in ENABLED_CRAWLERS if s.strip()]
    results = []
    with SessionLocal() as session:
        before = session.query(Post).count()
        for site_code in enabled:
            try:
                crawler = CrawlerRegistry.get_crawler(site_code)
                crawler.run(session)
                results.append({"crawler": site_code, "ok": True})
            except Exception as exc:
                logger.warning("크롤러 실패 %s: %s", site_code, exc)
                results.append({"crawler": site_code, "error": str(exc)})
        after = session.query(Post).count()

    return {"results": results, "new_posts": after - before, "total_posts": after}


def _handle_hd_render(job: Job) -> dict:
    post_id = job.post_id

    from db.session import SessionLocal
    from db.models import Post, Content, PostStatus
    from config.settings import MEDIA_DIR

    with SessionLocal() as db:
        post = db.query(Post).filter_by(id=post_id).first()
        content = db.query(Content).filter_by(post_id=post_id).first()
        if not post or not content:
            raise ValueError("Post/Content not found")

    output_path = str(Path(MEDIA_DIR) / "videos" / f"{post_id}_FHD.mp4")
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    from ai_worker.renderer.composer import render_final_video
    render_final_video(post, content, output_path=output_path)

    with SessionLocal() as db:
        db.query(Content).filter_by(post_id=post_id).update({"video_path": output_path})
        db.query(Post).filter_by(id=post_id).update({"status": PostStatus.RENDERED})
        db.commit()

    return {"video_path": output_path}


def _handle_upload(job: Job) -> dict:
    payload = job.payload or {}
    post_id = job.post_id
    platform = payload.get("platform", "youtube")

    from db.session import SessionLocal
    from db.models import Post, Content
    from uploaders.uploader import upload_post

    with SessionLocal() as db:
        post = db.query(Post).filter_by(id=post_id).first()
        content = db.query(Content).filter_by(post_id=post_id).first()
        result = upload_post(post, content, db, target_platform=platform)
    return {"platform": platform, "result": result}


def _handle_fetch_yt_analytics(job: Job) -> dict:
    post_id = job.post_id

    from db.session import SessionLocal
    from db.models import Content

    with SessionLocal() as db:
        content = db.query(Content).filter_by(post_id=post_id).first()
        if not content or not content.upload_meta:
            raise ValueError("upload_meta 없음")
        video_id = (content.upload_meta or {}).get("youtube", {}).get("video_id")
    if not video_id:
        raise ValueError("YouTube video_id 없음")

    from uploaders.youtube import YouTubeUploader
    uploader = YouTubeUploader()
    analytics = uploader.fetch_analytics(video_id)
    return {"analytics": analytics}


def _handle_ai_insight(job: Job) -> dict:
    from analytics.feedback import generate_structured_insights, build_performance_summary
    from analytics.collector import collect_analytics
    from config.settings import load_pipeline_config
    from db.session import SessionLocal

    cfg = load_pipeline_config()
    collect_analytics()
    with SessionLocal() as db:
        performance_data = build_performance_summary(db)
    insights = generate_structured_insights(performance_data, llm_model=cfg.get("llm_model", "haiku"))
    return {"insights": insights}


def _handle_feedback_apply(job: Job) -> dict:
    from analytics.feedback import generate_structured_insights, build_performance_summary, apply_feedback
    from analytics.collector import collect_analytics
    from config.settings import load_pipeline_config
    from db.session import SessionLocal

    cfg = load_pipeline_config()
    collect_analytics()
    with SessionLocal() as db:
        performance_data = build_performance_summary(db)
    insights = generate_structured_insights(performance_data, llm_model=cfg.get("llm_model", "haiku"))
    apply_feedback(insights)
    return {"applied": True}


def _handle_ab_create(job: Job) -> dict:
    """A/B 테스트 생성."""
    payload = job.payload or {}
    name = payload.get("name")
    preset_a = payload.get("preset_a")
    preset_b = payload.get("preset_b")
    if not (name and preset_a and preset_b):
        raise ValueError("AB_CREATE: name, preset_a, preset_b 필수")

    from analytics.ab_test import create_test
    test = create_test(name, preset_a, preset_b)
    return {"group_id": test.group_id, "name": test.name, "status": test.status}


def _handle_ab_evaluate(job: Job) -> dict:
    """A/B 그룹 성과 평가 — winner 결정."""
    payload = job.payload or {}
    group_id = payload.get("group_id")
    if not group_id:
        raise ValueError("AB_EVALUATE: group_id 필수")

    from analytics.ab_test import evaluate_group
    from db.session import SessionLocal

    with SessionLocal() as db:
        winner = evaluate_group(group_id, db)
    return {"group_id": group_id, "winner": winner}


def _handle_ab_apply_winner(job: Job) -> dict:
    """A/B 승자 설정을 feedback_config에 반영."""
    payload = job.payload or {}
    group_id = payload.get("group_id")
    if not group_id:
        raise ValueError("AB_APPLY_WINNER: group_id 필수")

    from analytics.ab_test import apply_winner

    ok = apply_winner(group_id)
    return {"group_id": group_id, "applied": ok}


# ---------------------------------------------------------------------------
# 핸들러 레지스트리
# ---------------------------------------------------------------------------
HANDLERS = {
    JobType.GENERATE_SCRIPT:    _handle_generate_script,
    JobType.TTS_PREVIEW:        _handle_tts_preview,
    JobType.AI_FITNESS:         _handle_ai_fitness,
    JobType.MANUAL_CRAWL:       _handle_manual_crawl,
    JobType.HD_RENDER:          _handle_hd_render,
    JobType.UPLOAD:             _handle_upload,
    JobType.FETCH_YT_ANALYTICS: _handle_fetch_yt_analytics,
    JobType.AI_INSIGHT:         _handle_ai_insight,
    JobType.FEEDBACK_APPLY:     _handle_feedback_apply,
    JobType.AB_EVALUATE:        _handle_ab_evaluate,
    JobType.AB_APPLY_WINNER:    _handle_ab_apply_winner,
    JobType.AB_CREATE:          _handle_ab_create,
}
