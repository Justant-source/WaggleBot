package com.wagglebot.job;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.wagglebot.common.JobStatus;
import com.wagglebot.common.JobType;
import com.wagglebot.domain.Job;
import com.wagglebot.domain.JobRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.Map;

@Service
@RequiredArgsConstructor
@Slf4j
public class JobService {

    private final JobRepository jobRepository;
    private static final ObjectMapper MAPPER = new ObjectMapper();

    @Transactional
    public Job createJob(JobType jobType, Long postId, Map<String, Object> payload) {
        Job job = new Job();
        job.setJobType(jobType);
        job.setPostId(postId);
        job.setStatus(JobStatus.PENDING);
        if (payload != null && !payload.isEmpty()) {
            try {
                String json = MAPPER.writeValueAsString(payload);
                job.setPayload(MAPPER.readTree(json));
            } catch (Exception e) {
                log.warn("Job payload 직렬화 실패: {}", e.getMessage());
            }
        }
        job.setCreatedAt(LocalDateTime.now());
        job.setUpdatedAt(LocalDateTime.now());
        return jobRepository.save(job);
    }

    public Job getJob(Long jobId) {
        return jobRepository.findById(jobId)
            .orElseThrow(() -> new IllegalArgumentException("Job not found: " + jobId));
    }
}
