package com.wagglebot.domain;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.JpaSpecificationExecutor;

public interface LlmLogRepository extends JpaRepository<LlmLog, Long>, JpaSpecificationExecutor<LlmLog> {
    Page<LlmLog> findByCallType(String callType, Pageable pageable);
    Page<LlmLog> findByPostId(Long postId, Pageable pageable);
    Page<LlmLog> findBySuccess(Boolean success, Pageable pageable);
}
