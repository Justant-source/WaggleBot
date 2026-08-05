package com.wagglebot.controller;

import com.wagglebot.settings.VoiceCatalogService;
import lombok.RequiredArgsConstructor;
import org.springframework.core.io.FileSystemResource;
import org.springframework.core.io.Resource;
import org.springframework.http.*;
import org.springframework.web.bind.annotation.*;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
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

    /**
     * Stream a preview sample for a voice key (ref wav or voice_preview_*.mp3).
     * Prefer this over /api/media/voices/... when filenames contain spaces/commas.
     */
    @GetMapping("/voices/{key}/sample")
    public ResponseEntity<Resource> getVoiceSample(@PathVariable String key) throws IOException {
        Path file = voiceCatalogService.resolveSampleFile(key);
        if (file == null || !Files.isRegularFile(file)) {
            return ResponseEntity.notFound().build();
        }
        String contentType = Files.probeContentType(file);
        if (contentType == null) {
            contentType = file.getFileName().toString().endsWith(".mp3") ? "audio/mpeg" : "audio/wav";
        }
        return ResponseEntity.ok()
            .contentType(MediaType.parseMediaType(contentType))
            .header(HttpHeaders.CONTENT_DISPOSITION, "inline; filename=\"" + file.getFileName() + "\"")
            .body(new FileSystemResource(file));
    }
}
