package com.wagglebot.controller;

import com.wagglebot.settings.SettingsService;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

@RestController
@RequestMapping("/api/settings")
@RequiredArgsConstructor
public class SettingsController {

    private final SettingsService settingsService;

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
}
