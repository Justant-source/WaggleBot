package com.wagglebot.controller;

import com.wagglebot.common.JobType;
import com.wagglebot.common.PostStatus;
import com.wagglebot.domain.*;
import com.wagglebot.job.JobService;
import lombok.RequiredArgsConstructor;
import org.springframework.data.domain.*;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.*;

@RestController
@RequestMapping("/api/inbox")
@RequiredArgsConstructor
public class InboxController {

    private final PostRepository postRepo;
    private final CommentRepository commentRepo;
    private final JobService jobService;

    @GetMapping
    public ResponseEntity<Map<String, Object>> list(
        @RequestParam(defaultValue = "0") int page,
        @RequestParam(defaultValue = "20") int size,
        @RequestParam(required = false) String siteCode,
        @RequestParam(required = false) String q,
        @RequestParam(required = false) String tier,
        @RequestParam(required = false) String sort,
        @RequestParam(required = false) String since,
        @RequestParam(required = false) Boolean recommended
    ) {
        Sort pageSort;
        if ("ai_score".equals(sort)) {
            pageSort = Sort.by(Sort.Order.desc("aiScore")).and(Sort.by(Sort.Order.desc("engagementScore")));
        } else if ("newest".equals(sort)) {
            pageSort = Sort.by("createdAt").descending();
        } else {
            pageSort = Sort.by("engagementScore").descending();
        }
        Pageable pageable = PageRequest.of(page, size, pageSort);
        Page<Post> posts = postRepo.findAll(
            (root, query, cb) -> {
                var predicates = new ArrayList<jakarta.persistence.criteria.Predicate>();
                predicates.add(cb.equal(root.get("status"), PostStatus.COLLECTED));
                if (siteCode != null && !siteCode.isBlank())
                    predicates.add(cb.equal(root.get("siteCode"), siteCode));
                if (q != null && !q.isBlank())
                    predicates.add(cb.like(cb.lower(root.get("title")), "%" + q.toLowerCase() + "%"));
                if ("tier1".equals(tier))
                    predicates.add(cb.greaterThanOrEqualTo(root.get("engagementScore"), 80.0));
                else if ("tier2".equals(tier))
                    predicates.add(cb.between(root.get("engagementScore"), 30.0, 79.99));
                else if ("tier3".equals(tier))
                    predicates.add(cb.lessThan(root.get("engagementScore"), 30.0));
                if (since != null && !since.isBlank()) {
                    LocalDateTime dt = LocalDateTime.parse(since, DateTimeFormatter.ISO_DATE_TIME);
                    predicates.add(cb.greaterThanOrEqualTo(root.get("createdAt"), dt));
                }
                if (recommended != null && recommended) {
                    predicates.add(cb.equal(root.get("aiRecommended"), true));
                }
                return cb.and(predicates.toArray(new jakarta.persistence.criteria.Predicate[0]));
            },
            pageable
        );
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("posts", posts.getContent());
        body.put("total", posts.getTotalElements());
        body.put("page", page);
        body.put("size", size);
        long tier1Count = postRepo.countByStatusAndScoreGte(PostStatus.COLLECTED, 80.0);
        long tier2Count = postRepo.countByStatusAndScoreBetween(PostStatus.COLLECTED, 30.0, 80.0);
        long totalCollected = postRepo.countByStatus(PostStatus.COLLECTED);
        body.put("counts", Map.of(
            "tier1", tier1Count,
            "tier2", tier2Count,
            "tier3", Math.max(0L, totalCollected - tier1Count - tier2Count)
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
        int processed = 0;
        List<Map<String, Object>> failed = new ArrayList<>();
        for (Integer id : ids) {
            try {
                if ("approve".equals(action)) approve(id.longValue());
                else if ("decline".equals(action)) decline(id.longValue());
                processed++;
            } catch (Exception e) {
                Map<String, Object> failEntry = new LinkedHashMap<>();
                failEntry.put("id", id);
                failEntry.put("error", e.getMessage() != null ? e.getMessage() : e.getClass().getSimpleName());
                failed.add(failEntry);
            }
        }
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("processed", processed);
        body.put("failed", failed);
        body.put("action", action);
        return ResponseEntity.ok(body);
    }

    @GetMapping("/{id}/comments")
    public ResponseEntity<Map<String, Object>> getComments(
        @PathVariable Long id,
        @RequestParam(defaultValue = "5") int limit
    ) {
        List<Map<String, Object>> comments = commentRepo.findByPostIdOrderByLikesDesc(id)
            .stream()
            .limit(limit)
            .map(c -> {
                Map<String, Object> m = new LinkedHashMap<>();
                m.put("id", c.getId());
                m.put("author", c.getAuthor());
                m.put("content", c.getContent());
                m.put("likes", c.getLikes());
                return m;
            })
            .toList();
        return ResponseEntity.ok(Map.of("comments", comments));
    }

    @PostMapping("/analyze-batch")
    public ResponseEntity<Map<String, Object>> analyzeBatch(
        @RequestBody(required = false) AnalyzeBatchRequest req
    ) {
        List<Long> ids;
        int limit = req != null && req.limit() > 0 ? Math.min(req.limit(), 20) : 20;
        if (req != null && req.ids() != null && !req.ids().isEmpty()) {
            ids = req.ids().stream().limit(20).toList();
        } else {
            ids = postRepo.findAll(
                (root, query, cb) -> cb.and(
                    cb.equal(root.get("status"), PostStatus.COLLECTED),
                    cb.isNull(root.get("aiScore"))
                ),
                PageRequest.of(0, limit, Sort.by("engagementScore").descending())
            ).map(Post::getId).toList();
        }
        List<Long> jobIds = new ArrayList<>();
        for (Long postId : ids) {
            var job = jobService.createJob(JobType.AI_FITNESS, postId, null);
            jobIds.add(job.getId());
        }
        return ResponseEntity.ok(Map.of("enqueued", jobIds.size(), "jobIds", jobIds));
    }

    public record AnalyzeBatchRequest(List<Long> ids, int limit) {}

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
