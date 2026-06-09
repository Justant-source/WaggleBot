package com.wagglebot.domain;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

public interface LlmLogRepository extends JpaRepository<LlmLog, Long> {
    Page<LlmLog> findByCallType(String callType, Pageable pageable);
    Page<LlmLog> findByPostId(Long postId, Pageable pageable);
    Page<LlmLog> findBySuccess(Boolean success, Pageable pageable);
}
