package com.wagglebot.llmworker;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.Map;
import java.util.concurrent.TimeoutException;

@RestController
public class LlmController {

    @Autowired
    private ClaudeService claudeService;

    @PostMapping("/v1/invoke")
    public ResponseEntity<Map<String, Object>> invoke(@RequestBody InvokeRequest req) {
        try {
            long timeoutMs = req.timeoutMs != null ? req.timeoutMs : 120_000L;
            String text = claudeService.invoke(req.prompt, req.model, req.jsonMode, timeoutMs);
            return ResponseEntity.ok(Map.of("text", text));
        } catch (TimeoutException e) {
            return ResponseEntity.status(504).body(Map.of("error", "timeout", "text", ""));
        } catch (Exception e) {
            return ResponseEntity.status(500).body(Map.of("error", e.getMessage(), "text", ""));
        }
    }

    @GetMapping("/healthz")
    public ResponseEntity<Map<String, String>> health() {
        return ResponseEntity.ok(Map.of("status", "ok"));
    }
}
