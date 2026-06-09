package com.wagglebot.domain;

import com.wagglebot.common.JobStatus;
import com.wagglebot.common.JobType;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;

public interface JobRepository extends JpaRepository<Job, Long> {
    Optional<Job> findTopByStatusOrderByCreatedAtAsc(JobStatus status);
    List<Job> findByPostIdAndJobTypeOrderByCreatedAtDesc(Long postId, JobType jobType);
}
