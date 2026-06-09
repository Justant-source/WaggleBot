package com.wagglebot.controller;

import com.wagglebot.domain.LlmLog;
import com.wagglebot.domain.LlmLogRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.data.domain.*;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/llm-logs")
@RequiredArgsConstructor
public class LlmLogController {

    private final LlmLogRepository logRepo;

    @GetMapping
    public ResponseEntity<Page<LlmLog>> list(
        @RequestParam(defaultValue = "0") int page,
        @RequestParam(defaultValue = "20") int size,
        @RequestParam(required = false) String callType,
        @RequestParam(required = false) Long postId,
        @RequestParam(required = false) Boolean success
    ) {
        Pageable pageable = PageRequest.of(page, size, Sort.by("createdAt").descending());
        if (callType != null) return ResponseEntity.ok(logRepo.findByCallType(callType, pageable));
        if (postId != null) return ResponseEntity.ok(logRepo.findByPostId(postId, pageable));
        if (success != null) return ResponseEntity.ok(logRepo.findBySuccess(success, pageable));
        return ResponseEntity.ok(logRepo.findAll(pageable));
    }

    @GetMapping("/{id}")
    public ResponseEntity<LlmLog> get(@PathVariable Long id) {
        return ResponseEntity.ok(
            logRepo.findById(id).orElseThrow(() -> new IllegalArgumentException("Log not found: " + id))
        );
    }
}
