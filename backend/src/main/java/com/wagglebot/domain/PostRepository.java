package com.wagglebot.domain;

import com.wagglebot.common.PostStatus;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.jpa.repository.JpaSpecificationExecutor;

import java.util.List;

public interface PostRepository extends JpaRepository<Post, Long>, JpaSpecificationExecutor<Post> {
    List<Post> findByStatusOrderByEngagementScoreDesc(PostStatus status);

    @Query("SELECT COUNT(p) FROM Post p WHERE p.status = :status")
    long countByStatus(PostStatus status);
}
