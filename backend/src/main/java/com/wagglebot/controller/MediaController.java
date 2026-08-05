package com.wagglebot.controller;

import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.FileSystemResource;
import org.springframework.core.io.Resource;
import org.springframework.http.*;
import org.springframework.web.bind.annotation.*;

import java.io.IOException;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;

@RestController
@RequestMapping("/api/media")
@Slf4j
public class MediaController {

    private final Path mediaDir;

    public MediaController(@Value("${app.media-dir:/app/media}") String mediaDirStr) {
        this.mediaDir = Path.of(mediaDirStr);
    }

    @GetMapping("/**")
    public ResponseEntity<Resource> serveMedia(jakarta.servlet.http.HttpServletRequest request) throws IOException {
        String uri = request.getRequestURI();
        String path = uri.replaceFirst("^/api/media/", "");
        path = URLDecoder.decode(path, StandardCharsets.UTF_8);
        Path file = mediaDir.resolve(path).normalize();
        if (!file.startsWith(mediaDir) || !Files.exists(file)) {
            return ResponseEntity.notFound().build();
        }
        String contentType = Files.probeContentType(file);
        if (contentType == null) contentType = "application/octet-stream";
        return ResponseEntity.ok()
            .contentType(MediaType.parseMediaType(contentType))
            .header(HttpHeaders.CONTENT_DISPOSITION, "inline; filename=\"" + file.getFileName() + "\"")
            .body(new FileSystemResource(file));
    }
}
