package com.wagglebot.controller;

import com.wagglebot.common.JobType;
import com.wagglebot.common.PostStatus;
import com.wagglebot.domain.*;
import com.wagglebot.job.JobService;
import lombok.RequiredArgsConstructor;
import org.springframework.data.domain.*;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.*;

@RestController
@RequestMapping("/api/inbox")
@RequiredArgsConstructor
public class InboxController {

    private final PostRepository postRepo;
    private final JobService jobService;

    @GetMapping
    public ResponseEntity<Map<String, Object>> list(
        @RequestParam(defaultValue = "0") int page,
        @RequestParam(defaultValue = "20") int size
    ) {
        Pageable pageable = PageRequest.of(page, size, Sort.by("engagementScore").descending());
        Page<Post> posts = postRepo.findAll(
            (root, q, cb) -> cb.equal(root.get("status"), PostStatus.COLLECTED),
            pageable
        );
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("posts", posts.getContent());
        body.put("total", posts.getTotalElements());
        body.put("page", page);
        body.put("size", size);
        body.put("counts", Map.of(
            "tier1", posts.getContent().stream().filter(p -> p.getEngagementScore() >= 80).count(),
            "tier2", posts.getContent().stream().filter(p -> p.getEngagementScore() >= 30 && p.getEngagementScore() < 80).count(),
            "tier3", posts.getContent().stream().filter(p -> p.getEngagementScore() < 30).count()
        ));
        return ResponseEntity.ok(body);
    }

    @PostMapping("/{id}/approve")
    public ResponseEntity<Map<String, Object>> approve(@PathVariable Long id) {
        Post post = postRepo.findById(id).orElseThrow(() -> new IllegalArgumentException("Post not found: " + id));
        post.setStatus(PostStatus.EDITING);
        postRepo.save(post);
        var job = jobService.createJob(JobType.GENERATE_SCRIPT, id, Map.of("call_type", "generate_script_auto"));
        return ResponseEntity.ok(Map.of("postId", id, "status", "EDITING", "jobId", job.getId()));
    }

    @PostMapping("/{id}/decline")
    public ResponseEntity<Map<String, Object>> decline(@PathVariable Long id) {
        Post post = postRepo.findById(id).orElseThrow(() -> new IllegalArgumentException("Post not found: " + id));
        post.setStatus(PostStatus.DECLINED);
        postRepo.save(post);
        return ResponseEntity.ok(Map.of("postId", id, "status", "DECLINED"));
    }

    @PostMapping("/batch")
    public ResponseEntity<Map<String, Object>> batch(@RequestBody Map<String, Object> req) {
        List<Integer> ids = (List<Integer>) req.get("ids");
        String action = (String) req.get("action");
        int count = 0;
        for (Integer id : ids) {
            try {
                if ("approve".equals(action)) approve(id.longValue());
                else if ("decline".equals(action)) decline(id.longValue());
                count++;
            } catch (Exception ignored) {}
        }
        return ResponseEntity.ok(Map.of("processed", count, "action", action));
    }

    @PostMapping("/{id}/analyze")
    public ResponseEntity<Map<String, Object>> analyze(@PathVariable Long id) {
        var job = jobService.createJob(JobType.AI_FITNESS, id, null);
        return ResponseEntity.ok(Map.of("jobId", job.getId()));
    }

    @PostMapping("/crawl")
    public ResponseEntity<Map<String, Object>> crawl() {
        var job = jobService.createJob(JobType.MANUAL_CRAWL, null, null);
        return ResponseEntity.ok(Map.of("jobId", job.getId()));
    }

    @GetMapping("/jobs/{jobId}")
    public ResponseEntity<Map<String, Object>> pollJob(@PathVariable Long jobId) {
        var job = jobService.getJob(jobId);
        return ResponseEntity.ok(Map.of(
            "id", job.getId(),
            "status", job.getStatus(),
            "result", job.getResult() != null ? job.getResult() : Map.of(),
            "error", job.getError() != null ? job.getError() : ""
        ));
    }
}
