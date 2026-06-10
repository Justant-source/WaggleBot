package com.wagglebot.controller;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.wagglebot.common.PostStatus;
import com.wagglebot.domain.ContentRepository;
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
    private final ContentRepository contentRepo;
    private final ObjectMapper objectMapper;

    @GetMapping
    public ResponseEntity<Map<String, Object>> getProgress() {
        Map<String, Long> counts = new LinkedHashMap<>();
        for (PostStatus status : PostStatus.values()) {
            counts.put(status.name(), postRepo.countByStatus(status));
        }
        List<com.wagglebot.domain.Post> processingPosts = postRepo.findAll(
            (root, q, cb) -> cb.equal(root.get("status"), PostStatus.PROCESSING)
        );
        List<Map<String, Object>> processing = processingPosts.stream().map(post -> {
            Map<String, Object> item = new LinkedHashMap<>();
            item.put("id", post.getId());
            item.put("title", post.getTitle());
            item.put("siteCode", post.getSiteCode());
            item.put("updatedAt", post.getUpdatedAt());
            contentRepo.findByPostId(post.getId()).ifPresent(c -> {
                String ps = c.getPipelineState() != null ? c.getPipelineState().toString() : null;
                item.put("progress", parseProgress(ps));
            });
            if (!item.containsKey("progress")) item.put("progress", null);
            return item;
        }).toList();
        List<com.wagglebot.domain.Post> failed = postRepo.findTop20ByStatusOrderByUpdatedAtDesc(PostStatus.FAILED);
        return ResponseEntity.ok(Map.of("counts", counts, "processing", processing, "failed", failed));
    }

    @PostMapping("/{id}/retry")
    public ResponseEntity<Map<String, Object>> retry(@PathVariable Long id) {
        int updated = postRepo.resetForRetry(id);
        if (updated == 0) throw new IllegalArgumentException("Post not found: " + id);
        return ResponseEntity.ok(Map.of("postId", id, "status", "APPROVED"));
    }

    @SuppressWarnings("unchecked")
    Map<String, Object> parseProgress(String pipelineState) {
        if (pipelineState == null) return null;
        try {
            Map<String, Object> state = objectMapper.readValue(pipelineState, Map.class);
            Map<String, Object> raw = (Map<String, Object>) state.get("progress");
            if (raw != null) return toCamel(raw);
            // 레거시 폴백: video_scenes_done 키 존재 시
            if (state.containsKey("video_scenes_done")) {
                List<?> done = (List<?>) state.get("video_scenes_done");
                Map<String, Object> legacy = new LinkedHashMap<>();
                legacy.put("currentPhase", 7);
                legacy.put("phaseName", "비디오 클립");
                legacy.put("scenesDone", done.size());
                legacy.put("totalScenes", state.getOrDefault("total_scenes", 0));
                return legacy;
            }
        } catch (Exception ignored) {}
        return null;
    }

    /** snake_case 키 → camelCase 변환 (Python progress 맵을 TypeScript 타입에 맞춤). */
    private static Map<String, Object> toCamel(Map<String, Object> src) {
        Map<String, Object> out = new LinkedHashMap<>();
        src.forEach((k, v) -> out.put(snakeToCamel(k), v));
        return out;
    }

    private static String snakeToCamel(String s) {
        int idx = s.indexOf('_');
        if (idx < 0) return s;
        StringBuilder sb = new StringBuilder(s.length());
        boolean up = false;
        for (int i = 0; i < s.length(); i++) {
            char c = s.charAt(i);
            if (c == '_') { up = true; }
            else { sb.append(up ? Character.toUpperCase(c) : c); up = false; }
        }
        return sb.toString();
    }
}
