package com.wagglebot.controller;

import com.wagglebot.settings.BgmCatalogService;
import lombok.RequiredArgsConstructor;
import org.springframework.core.io.FileSystemResource;
import org.springframework.core.io.Resource;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;

@RestController
@RequestMapping("/api/bgm")
@RequiredArgsConstructor
public class BgmController {

    private final BgmCatalogService bgmCatalogService;

    @GetMapping("/tracks")
    public ResponseEntity<Map<String, Object>> getBgmTracks() {
        return ResponseEntity.ok(Map.of(
            "tracks", bgmCatalogService.loadBgmTracks()
        ));
    }

    /**
     * Stream a BGM sample by emotion and filename.
     * Path: /api/bgm/sample/{emotion}/{filename}
     * Example: /api/bgm/sample/hype/hype_01.mp3
     */
    @GetMapping("/sample/{emotion}/{filename}")
    public ResponseEntity<Resource> getBgmSample(
        @PathVariable String emotion,
        @PathVariable String filename
    ) throws IOException {
        Path file = bgmCatalogService.resolveSampleFile(emotion, filename);
        if (file == null || !Files.isRegularFile(file)) {
            return ResponseEntity.notFound().build();
        }

        String contentType = Files.probeContentType(file);
        if (contentType == null) {
            contentType = "audio/mpeg"; // Default to mp3
        }

        return ResponseEntity.ok()
            .contentType(MediaType.parseMediaType(contentType))
            .header(HttpHeaders.CONTENT_DISPOSITION, "inline; filename=\"" + file.getFileName() + "\"")
            .body(new FileSystemResource(file));
    }
}
