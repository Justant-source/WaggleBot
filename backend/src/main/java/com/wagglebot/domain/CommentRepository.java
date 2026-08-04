package com.wagglebot.domain;

import org.springframework.data.jpa.repository.JpaRepository;
import java.util.List;

public interface CommentRepository extends JpaRepository<Comment, Long> {
    List<Comment> findByPostIdOrderByLikesDesc(Long postId);

    /** uq_post_comment (post_id, author, content_hash)와 동일 키 — 외부 ingest 재시도 시 중복 삽입 방지. */
    boolean existsByPostIdAndAuthorAndContentHash(Long postId, String author, String contentHash);
}
