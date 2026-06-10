package com.wagglebot.controller;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.wagglebot.common.PostStatus;
import com.wagglebot.domain.ContentRepository;
import com.wagglebot.domain.PostRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.*;

@RestController
@RequestMapping("/api/overview")
@RequiredArgsConstructor
public class OverviewController {

    private final PostRepository postRepository;
    private final ContentRepository contentRepository;
    private final ObjectMapper objectMapper;

    @GetMapping
    public ResponseEntity<Map<String, Object>> getOverview(
        @RequestParam(required = false) String since
    ) {
        LocalDateTime sinceTime = since != null && !since.isBlank()
            ? LocalDateTime.parse(since, DateTimeFormatter.ISO_DATE_TIME)
            : LocalDate.now().atStartOfDay();

        // 각 status별 카운트
        Map<String, Long> counts = new LinkedHashMap<>();
        for (PostStatus status : PostStatus.values()) {
            counts.put(status.name(), postRepository.countByStatus(status));
        }

        // 오늘(since 기준) 집계
        long crawled = postRepository.countByCreatedAtAfter(sinceTime);
        long uploaded = postRepository.countByStatusAndUpdatedAtAfter(PostStatus.UPLOADED, sinceTime);
        long declined = postRepository.countByStatusAndUpdatedAtAfter(PostStatus.DECLINED, sinceTime);
        Map<String, Object> today = new LinkedHashMap<>();
        today.put("crawled", crawled);
        today.put("uploaded", uploaded);
        today.put("declined", declined);

        // 최근 실패 5개
        List<com.wagglebot.domain.Post> failedRecent = postRepository
            .findTop20ByStatusOrderByUpdatedAtDesc(PostStatus.FAILED)
            .stream().limit(5).toList();

        // PROCESSING 목록 + progress enrich
        List<com.wagglebot.domain.Post> processingPosts = postRepository.findAll(
            (root, q, cb) -> cb.equal(root.get("status"), PostStatus.PROCESSING)
        );
        List<Map<String, Object>> processing = processingPosts.stream().map(post -> {
            Map<String, Object> item = new LinkedHashMap<>();
            item.put("id", post.getId());
            item.put("title", post.getTitle());
            item.put("siteCode", post.getSiteCode());
            item.put("updatedAt", post.getUpdatedAt());
            contentRepository.findByPostId(post.getId()).ifPresent(c -> {
                String ps = c.getPipelineState() != null ? c.getPipelineState().toString() : null;
                item.put("progress", parseProgress(ps));
            });
            if (!item.containsKey("progress")) item.put("progress", null);
            return item;
        }).toList();

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("counts", counts);
        result.put("today", today);
        result.put("sinceTime", sinceTime.toString());
        result.put("failedRecent", failedRecent);
        result.put("processing", processing);
        return ResponseEntity.ok(result);
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> parseProgress(String pipelineState) {
        if (pipelineState == null) return null;
        try {
            Map<String, Object> state = objectMapper.readValue(pipelineState, Map.class);
            Map<String, Object> raw = (Map<String, Object>) state.get("progress");
            if (raw != null) return toCamel(raw);
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
