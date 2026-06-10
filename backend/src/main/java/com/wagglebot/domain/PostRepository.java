package com.wagglebot.domain;

import com.wagglebot.common.PostStatus;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.JpaSpecificationExecutor;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.util.List;

public interface PostRepository extends JpaRepository<Post, Long>, JpaSpecificationExecutor<Post> {
    List<Post> findByStatusOrderByEngagementScoreDesc(PostStatus status);

    List<Post> findTop20ByStatusOrderByUpdatedAtDesc(PostStatus status);

    @Query("SELECT COUNT(p) FROM Post p WHERE p.status = :status")
    long countByStatus(@Param("status") PostStatus status);

    @Query("SELECT COUNT(p) FROM Post p WHERE p.status = :status AND p.engagementScore >= :minScore")
    long countByStatusAndScoreGte(@Param("status") PostStatus status, @Param("minScore") double minScore);

    @Query("SELECT COUNT(p) FROM Post p WHERE p.status = :status AND p.engagementScore >= :low AND p.engagementScore < :high")
    long countByStatusAndScoreBetween(@Param("status") PostStatus status, @Param("low") double low, @Param("high") double high);
}
