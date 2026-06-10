package com.wagglebot.controller;

import com.wagglebot.common.JobType;
import com.wagglebot.common.PostStatus;
import com.wagglebot.domain.ContentRepository;
import com.wagglebot.domain.PostRepository;
import com.wagglebot.job.JobService;
import com.wagglebot.settings.SettingsService;
import lombok.RequiredArgsConstructor;
import org.springframework.data.domain.PageRequest;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.*;

@RestController
@RequestMapping("/api/analytics")
@RequiredArgsConstructor
public class AnalyticsController {

    private final PostRepository postRepo;
    private final ContentRepository contentRepo;
    private final JobService jobService;
    private final SettingsService settingsService;

    @GetMapping("/funnel")
    public ResponseEntity<Map<String, Long>> funnel() {
        Map<String, Long> counts = new LinkedHashMap<>();
        for (PostStatus s : PostStatus.values()) counts.put(s.name(), postRepo.countByStatus(s));
        return ResponseEntity.ok(counts);
    }

    @PostMapping("/youtube/fetch")
    public ResponseEntity<Map<String, Object>> fetchYt(@RequestBody(required = false) Map<String, Object> req) {
        Long postId = req != null && req.containsKey("postId") ? ((Number) req.get("postId")).longValue() : null;
        var job = jobService.createJob(JobType.FETCH_YT_ANALYTICS, postId, req);
        return ResponseEntity.ok(Map.of("jobId", job.getId()));
    }

    @PostMapping("/insights")
    public ResponseEntity<Map<String, Object>> insights() {
        var job = jobService.createJob(JobType.AI_INSIGHT, null, null);
        return ResponseEntity.ok(Map.of("jobId", job.getId()));
    }

    @PostMapping("/feedback/apply")
    public ResponseEntity<Map<String, Object>> feedbackApply() {
        var job = jobService.createJob(JobType.FEEDBACK_APPLY, null, null);
        return ResponseEntity.ok(Map.of("jobId", job.getId()));
    }

    @GetMapping("/performance")
    public ResponseEntity<List<Map<String, Object>>> performance(
        @RequestParam(defaultValue = "20") int limit
    ) {
        var posts = postRepo.findByStatusOrderByEngagementScoreDesc(PostStatus.UPLOADED)
            .stream().limit(limit).toList();
        List<Map<String, Object>> result = new ArrayList<>();
        for (var post : posts) {
            var contentOpt = contentRepo.findByPostId(post.getId());
            Map<String, Object> analytics = Map.of();
            String videoId = null;
            if (contentOpt.isPresent()) {
                var meta = contentOpt.get().getUploadMeta();
                if (meta != null && meta.has("youtube")) {
                    var yt = meta.get("youtube");
                    if (yt.has("video_id")) videoId = yt.get("video_id").asText();
                    if (yt.has("analytics")) {
                        var a = yt.get("analytics");
                        analytics = Map.of(
                            "views",    a.has("views")    ? a.get("views").asInt()    : 0,
                            "likes",    a.has("likes")    ? a.get("likes").asInt()    : 0,
                            "comments", a.has("comments") ? a.get("comments").asInt() : 0
                        );
                    }
                }
            }
            Map<String, Object> row = new LinkedHashMap<>();
            row.put("postId",  post.getId());
            row.put("title",   post.getTitle());
            row.put("videoId", videoId);
            row.put("analytics", analytics);
            result.add(row);
        }
        return ResponseEntity.ok(result);
    }

    @PostMapping("/ab/create")
    public ResponseEntity<Map<String, Object>> abCreate(@RequestBody Map<String, Object> req) {
        String name     = (String) req.get("name");
        String presetA  = (String) req.get("presetA");
        String presetB  = (String) req.get("presetB");
        if (name == null || presetA == null || presetB == null)
            return ResponseEntity.badRequest().body(Map.of("error", "name, presetA, presetB required"));
        var job = jobService.createJob(JobType.AB_CREATE, null,
            Map.of("name", name, "preset_a", presetA, "preset_b", presetB));
        return ResponseEntity.ok(Map.of("jobId", job.getId()));
    }

    @PostMapping("/ab/evaluate")
    public ResponseEntity<Map<String, Object>> abEvaluate(@RequestBody Map<String, Object> req) {
        String groupId = (String) req.get("groupId");
        if (groupId == null || groupId.isBlank()) return ResponseEntity.badRequest().body(Map.of("error", "groupId required"));
        var job = jobService.createJob(JobType.AB_EVALUATE, null, Map.of("group_id", groupId));
        return ResponseEntity.ok(Map.of("jobId", job.getId()));
    }

    @PostMapping("/ab/apply-winner")
    public ResponseEntity<Map<String, Object>> abApplyWinner(@RequestBody Map<String, Object> req) {
        String groupId = (String) req.get("groupId");
        if (groupId == null || groupId.isBlank()) return ResponseEntity.badRequest().body(Map.of("error", "groupId required"));
        var job = jobService.createJob(JobType.AB_APPLY_WINNER, null, Map.of("group_id", groupId));
        return ResponseEntity.ok(Map.of("jobId", job.getId()));
    }

    @GetMapping("/jobs/{jobId}")
    public ResponseEntity<Map<String, Object>> pollJob(@PathVariable Long jobId) {
        var job = jobService.getJob(jobId);
        return ResponseEntity.ok(Map.of(
            "id", job.getId(), "status", job.getStatus(),
            "result", job.getResult() != null ? job.getResult() : Map.of()
        ));
    }
}
