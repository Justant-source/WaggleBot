package com.wagglebot.controller;

import com.wagglebot.settings.VoiceCatalogService;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

@RestController
@RequestMapping("/api/tts")
@RequiredArgsConstructor
public class TtsController {

    private final VoiceCatalogService voiceCatalogService;

    @GetMapping("/voices")
    public ResponseEntity<Map<String, Object>> getVoices() {
        return ResponseEntity.ok(Map.of(
            "defaultVoice", voiceCatalogService.getDefaultVoice(),
            "voices", voiceCatalogService.loadVoices()
        ));
    }
}
