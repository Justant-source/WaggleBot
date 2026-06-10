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
        Page<LlmLog> result = logRepo.findAll((root, q, cb) -> {
            var predicates = new java.util.ArrayList<jakarta.persistence.criteria.Predicate>();
            if (callType != null && !callType.isBlank())
                predicates.add(cb.equal(root.get("callType"), callType));
            if (postId != null)
                predicates.add(cb.equal(root.get("postId"), postId));
            if (success != null)
                predicates.add(cb.equal(root.get("success"), success));
            return predicates.isEmpty() ? cb.conjunction()
                : cb.and(predicates.toArray(new jakarta.persistence.criteria.Predicate[0]));
        }, pageable);
        return ResponseEntity.ok(result);
    }

    @GetMapping("/{id}")
    public ResponseEntity<LlmLog> get(@PathVariable Long id) {
        return ResponseEntity.ok(
            logRepo.findById(id).orElseThrow(() -> new IllegalArgumentException("Log not found: " + id))
        );
    }
}
