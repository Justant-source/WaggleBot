package com.wagglebot.domain;

import com.wagglebot.common.PostStatus;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;

import java.util.List;

public interface PostRepository extends JpaRepository<Post, Long> {
    List<Post> findByStatusOrderByEngagementScoreDesc(PostStatus status);

    @Query("SELECT COUNT(p) FROM Post p WHERE p.status = :status")
    long countByStatus(PostStatus status);
}
