package com.wagglebot.domain;

import com.wagglebot.common.PostStatus;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.JpaSpecificationExecutor;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
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

    long countByCreatedAtAfter(LocalDateTime since);

    @Query("SELECT COUNT(p) FROM Post p WHERE p.status = :status AND p.updatedAt > :since")
    long countByStatusAndUpdatedAtAfter(@Param("status") PostStatus status, @Param("since") LocalDateTime since);

    @Query("SELECT DISTINCT p.siteCode FROM Post p WHERE p.siteCode IS NOT NULL ORDER BY p.siteCode")
    List<String> findDistinctSiteCodes();

    @Transactional
    @Modifying
    @Query("UPDATE Post p SET p.status = 'APPROVED', p.retryCount = p.retryCount + 1, p.lastError = NULL WHERE p.id = :id")
    int resetForRetry(@Param("id") Long id);
}
