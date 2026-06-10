"""YouTube Analytics 수집 — UPLOADED 포스트의 통계를 가져와 upload_meta에 저장."""

import logging

logger = logging.getLogger(__name__)


def collect_analytics(max_posts: int = 50) -> int:
    """UPLOADED 상태 포스트의 YouTube 통계를 수집해 upload_meta에 저장한다.

    Returns:
        업데이트된 포스트 수.
    """
    from db.session import SessionLocal
    from db.models import Post, Content, PostStatus
    from uploaders.youtube import YouTubeUploader

    updated = 0
    uploader = YouTubeUploader()

    with SessionLocal() as db:
        rows = (
            db.query(Post, Content)
            .join(Content, Content.post_id == Post.id)
            .filter(Post.status == PostStatus.UPLOADED)
            .limit(max_posts)
            .all()
        )

        for post, content in rows:
            meta = content.upload_meta or {}
            yt = meta.get("youtube", {})
            video_id = yt.get("video_id")
            if not video_id:
                continue

            stats = uploader.fetch_analytics(video_id)
            if stats is None:
                continue

            # 기존 analytics와 병합 (views 합산 아님, 최신값 덮어쓰기)
            yt["analytics"] = stats
            meta["youtube"] = yt
            content.upload_meta = dict(meta)
            updated += 1
            logger.info(
                "Analytics 수집 post_id=%s video_id=%s views=%s",
                post.id, video_id, stats.get("views"),
            )

        if updated:
            db.commit()

    logger.info("Analytics 수집 완료: %d개 업데이트", updated)
    return updated
