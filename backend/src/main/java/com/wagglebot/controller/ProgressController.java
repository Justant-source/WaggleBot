package com.wagglebot.controller;

import com.wagglebot.common.PostStatus;
import com.wagglebot.domain.PostRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.*;

@RestController
@RequestMapping("/api/progress")
@RequiredArgsConstructor
public class ProgressController {

    private final PostRepository postRepo;

    @GetMapping
    public ResponseEntity<Map<String, Object>> getProgress() {
        Map<String, Long> counts = new LinkedHashMap<>();
        for (PostStatus status : PostStatus.values()) {
            counts.put(status.name(), postRepo.countByStatus(status));
        }
        List<com.wagglebot.domain.Post> processing = postRepo.findAll(
            (root, q, cb) -> cb.equal(root.get("status"), PostStatus.PROCESSING)
        );
        return ResponseEntity.ok(Map.of("counts", counts, "processing", processing));
    }

    @PostMapping("/{id}/retry")
    public ResponseEntity<Map<String, Object>> retry(@PathVariable Long id) {
        var post = postRepo.findById(id).orElseThrow(() -> new IllegalArgumentException("Post not found: " + id));
        post.setStatus(PostStatus.APPROVED);
        post.setRetryCount(post.getRetryCount() + 1);
        postRepo.save(post);
        return ResponseEntity.ok(Map.of("postId", id, "status", "APPROVED"));
    }
}
