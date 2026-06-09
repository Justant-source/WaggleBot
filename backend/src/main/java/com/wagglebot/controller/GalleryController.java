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
@RequestMapping("/api/gallery")
@RequiredArgsConstructor
public class GalleryController {

    private final ContentRepository contentRepo;
    private final PostRepository postRepo;
    private final JobService jobService;

    @GetMapping
    public ResponseEntity<Map<String, Object>> list(
        @RequestParam(defaultValue = "0") int page,
        @RequestParam(defaultValue = "12") int size
    ) {
        List<PostStatus> statuses = List.of(PostStatus.PREVIEW_RENDERED, PostStatus.RENDERED, PostStatus.UPLOADED);
        Pageable pageable = PageRequest.of(page, size, Sort.by("updatedAt").descending());
        Page<Post> posts = postRepo.findAll(
            (root, q, cb) -> root.get("status").in(statuses),
            pageable
        );
        List<Map<String, Object>> items = posts.getContent().stream().map(post -> {
            Map<String, Object> item = new LinkedHashMap<>();
            item.put("post", post);
            contentRepo.findByPostId(post.getId()).ifPresent(c -> item.put("content", c));
            return item;
        }).toList();
        return ResponseEntity.ok(Map.of("items", items, "total", posts.getTotalElements(), "page", page));
    }

    @PostMapping("/{id}/hd-render")
    public ResponseEntity<Map<String, Object>> hdRender(@PathVariable Long id) {
        var job = jobService.createJob(JobType.HD_RENDER, id, null);
        return ResponseEntity.ok(Map.of("jobId", job.getId()));
    }

    @PostMapping("/{id}/upload")
    public ResponseEntity<Map<String, Object>> upload(
        @PathVariable Long id, @RequestBody(required = false) Map<String, Object> req
    ) {
        Map<String, Object> payload = req != null ? req : Map.of("platform", "youtube");
        var job = jobService.createJob(JobType.UPLOAD, id, payload);
        return ResponseEntity.ok(Map.of("jobId", job.getId()));
    }
}
