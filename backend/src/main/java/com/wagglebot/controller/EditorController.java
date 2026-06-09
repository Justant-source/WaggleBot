package com.wagglebot.controller;

import com.wagglebot.common.*;
import com.wagglebot.domain.*;
import com.wagglebot.job.JobService;
import com.wagglebot.settings.SettingsService;
import lombok.RequiredArgsConstructor;
import org.springframework.data.domain.*;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.*;

@RestController
@RequestMapping("/api/editor")
@RequiredArgsConstructor
public class EditorController {

    private final PostRepository postRepo;
    private final ContentRepository contentRepo;
    private final JobService jobService;
    private final ScriptDataMapper scriptMapper;
    private final SettingsService settingsService;

    @GetMapping
    public ResponseEntity<Page<Post>> list(
        @RequestParam(defaultValue = "0") int page,
        @RequestParam(defaultValue = "20") int size
    ) {
        Pageable pageable = PageRequest.of(page, size, Sort.by("createdAt").descending());
        Page<Post> posts = postRepo.findAll(
            (root, q, cb) -> cb.equal(root.get("status"), PostStatus.EDITING),
            pageable
        );
        return ResponseEntity.ok(posts);
    }

    @GetMapping("/{id}")
    public ResponseEntity<Map<String, Object>> get(@PathVariable Long id) {
        Post post = postRepo.findById(id).orElseThrow(() -> new IllegalArgumentException("Post not found: " + id));
        Optional<Content> content = contentRepo.findByPostId(id);
        ScriptDataDto script = content.map(c -> scriptMapper.fromJson(c.getSummaryText())).orElse(null);
        Map<String, Object> cfg = settingsService.loadPipelineConfig();
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("post", post);
        result.put("script", script);
        result.put("maxCharsPerLine", cfg.getOrDefault("max_chars_per_line", 20));
        result.put("maxBodyItems", cfg.getOrDefault("max_body_items", 23));
        return ResponseEntity.ok(result);
    }

    @PutMapping("/{id}/script")
    public ResponseEntity<Map<String, Object>> saveScript(
        @PathVariable Long id, @RequestBody ScriptDataDto dto
    ) {
        Content content = contentRepo.findByPostId(id).orElse(new Content());
        if (content.getPostId() == null) {
            content.setPostId(id);
            content.setCreatedAt(java.time.LocalDateTime.now());
        }
        content.setSummaryText(scriptMapper.toJson(dto));
        contentRepo.save(content);
        return ResponseEntity.ok(Map.of("saved", true));
    }

    @PostMapping("/{id}/generate")
    public ResponseEntity<Map<String, Object>> generate(
        @PathVariable Long id, @RequestBody(required = false) Map<String, Object> req
    ) {
        Map<String, Object> payload = new HashMap<>();
        payload.put("call_type", "generate_script_editor");
        if (req != null && req.containsKey("model")) payload.put("model", req.get("model"));
        if (req != null && req.containsKey("extra_instructions")) payload.put("extra_instructions", req.get("extra_instructions"));
        var job = jobService.createJob(JobType.GENERATE_SCRIPT, id, payload);
        return ResponseEntity.ok(Map.of("jobId", job.getId()));
    }

    @PostMapping("/{id}/tts-preview")
    public ResponseEntity<Map<String, Object>> ttsPreview(
        @PathVariable Long id, @RequestBody(required = false) Map<String, Object> req
    ) {
        Map<String, Object> payload = req != null ? req : new HashMap<>();
        var job = jobService.createJob(JobType.TTS_PREVIEW, id, payload);
        return ResponseEntity.ok(Map.of("jobId", job.getId()));
    }

    @PostMapping("/{id}/confirm")
    public ResponseEntity<Map<String, Object>> confirm(@PathVariable Long id) {
        Post post = postRepo.findById(id).orElseThrow(() -> new IllegalArgumentException("Post not found: " + id));
        post.setStatus(PostStatus.APPROVED);
        postRepo.save(post);
        return ResponseEntity.ok(Map.of("postId", id, "status", "APPROVED"));
    }

    @GetMapping("/jobs/{jobId}")
    public ResponseEntity<Map<String, Object>> pollJob(@PathVariable Long jobId) {
        var job = jobService.getJob(jobId);
        return ResponseEntity.ok(Map.of(
            "id", job.getId(), "status", job.getStatus(),
            "result", job.getResult() != null ? job.getResult() : Map.of(),
            "error", job.getError() != null ? job.getError() : ""
        ));
    }
}
