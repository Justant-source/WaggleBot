package com.wagglebot.controller;

import com.wagglebot.settings.SettingsService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.Map;

@RestController
@RequestMapping("/api/settings")
@RequiredArgsConstructor
@Slf4j
public class SettingsController {

    private final SettingsService settingsService;
    private static final HttpClient HTTP = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(3))
        .build();

    @GetMapping
    public ResponseEntity<Map<String, Object>> get() {
        return ResponseEntity.ok(settingsService.loadPipelineConfig());
    }

    @PutMapping
    public ResponseEntity<Map<String, Object>> save(@RequestBody Map<String, Object> config) throws Exception {
        settingsService.savePipelineConfig(config);
        return ResponseEntity.ok(Map.of("saved", true));
    }

    @GetMapping("/credentials")
    public ResponseEntity<Map<String, Object>> getCredentials() {
        Map<String, Object> creds = settingsService.loadCredentialsConfig();
        // 시크릿 값은 마스킹
        creds.replaceAll((k, v) -> v instanceof String s && s.length() > 4
            ? s.substring(0, 2) + "***" : v);
        return ResponseEntity.ok(creds);
    }

    @PutMapping("/credentials")
    public ResponseEntity<Map<String, Object>> saveCredentials(@RequestBody Map<String, Object> creds) throws Exception {
        settingsService.saveCredentialsConfig(creds);
        return ResponseEntity.ok(Map.of("saved", true));
    }

    @GetMapping("/health")
    public ResponseEntity<Map<String, Object>> health() {
        Map<String, Object> cfg = settingsService.loadPipelineConfig();
        String backend = String.valueOf(cfg.getOrDefault("llm_backend", "cli"));
        if ("api".equals(backend)) {
            // API 백엔드: credentials.json에 API 키가 있으면 ok
            Map<String, Object> creds = settingsService.loadCredentialsConfig();
            boolean hasKey = creds.containsKey("anthropic_api_key")
                && creds.get("anthropic_api_key") instanceof String s
                && !s.isBlank();
            return hasKey
                ? ResponseEntity.ok(Map.of("status", "ok", "backend", "api"))
                : ResponseEntity.status(503).body(Map.of("status", "error", "reason", "API 키 미설정"));
        }
        // CLI 백엔드: llm-worker 컨테이너 헬스 프로브
        try {
            var req = HttpRequest.newBuilder()
                .uri(URI.create("http://llm-worker:8090/actuator/health"))
                .timeout(Duration.ofSeconds(3))
                .GET()
                .build();
            var res = HTTP.send(req, HttpResponse.BodyHandlers.discarding());
            return res.statusCode() < 400
                ? ResponseEntity.ok(Map.of("status", "ok", "backend", "cli"))
                : ResponseEntity.status(503).body(Map.of("status", "error", "reason", "llm-worker 응답 이상"));
        } catch (Exception e) {
            log.debug("llm-worker 헬스체크 실패: {}", e.getMessage());
            return ResponseEntity.status(503).body(Map.of("status", "error", "reason", "llm-worker 연결 실패"));
        }
    }
}
