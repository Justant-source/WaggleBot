package com.wagglebot.settings;

import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.*;
import java.util.regex.Pattern;
import java.util.stream.Stream;

@Service
@Slf4j
public class BgmCatalogService {

    private static final Set<String> VALID_EMOTIONS = Set.of("shock", "anger", "tension", "sad", "hype");
    private static final Pattern BGM_FILENAME_PATTERN = Pattern.compile("^(shock|anger|tension|sad|hype)_0[12]\\.mp3$");

    private final Path mediaDir;

    public BgmCatalogService(@Value("${app.media-dir:/app/media}") String mediaDirStr) {
        this.mediaDir = Path.of(mediaDirStr);
    }

    /**
     * /app/media/bgm 디렉토리 스캔. 감정별 폴더에서 mp3 파일 열거.
     * 각 항목: {emotion, file, path, durationSec}
     */
    public List<Map<String, Object>> loadBgmTracks() {
        List<Map<String, Object>> result = new ArrayList<>();
        Path bgmDir = mediaBgmDir();

        if (!Files.isDirectory(bgmDir)) {
            log.warn("BGM directory not found: {}", bgmDir);
            return result;
        }

        // 감정별 폴더 순회
        for (String emotion : VALID_EMOTIONS) {
            Path emotionDir = bgmDir.resolve(emotion);
            if (!Files.isDirectory(emotionDir)) {
                continue;
            }

            try (Stream<Path> stream = Files.list(emotionDir)) {
                stream
                    .filter(p -> Files.isRegularFile(p))
                    .filter(p -> p.getFileName().toString().endsWith(".mp3"))
                    .filter(p -> BGM_FILENAME_PATTERN.matcher(p.getFileName().toString()).matches())
                    .sorted()
                    .forEach(p -> {
                        String filename = p.getFileName().toString();
                        Map<String, Object> entry = new LinkedHashMap<>();
                        entry.put("emotion", emotion);
                        entry.put("file", filename);
                        entry.put("path", String.format("/api/bgm/sample/%s/%s", emotion, filename));
                        entry.put("durationSec", getDurationSec(p));
                        result.add(entry);
                    });
            } catch (IOException e) {
                log.warn("Failed to list BGM directory {}: {}", emotionDir, e.getMessage());
            }
        }

        return result;
    }

    /**
     * Resolve a specific BGM file path.
     * emotion must match VALID_EMOTIONS, file must match {emotion}_0{1,2}.mp3 pattern
     */
    public Path resolveSampleFile(String emotion, String file) {
        if (emotion == null || file == null) {
            return null;
        }

        // Validate emotion
        if (!VALID_EMOTIONS.contains(emotion)) {
            log.debug("Invalid emotion: {}", emotion);
            return null;
        }

        // Validate filename pattern
        if (!file.matches("^" + emotion + "_0[12]\\.mp3$")) {
            log.debug("Invalid BGM filename pattern: {}", file);
            return null;
        }

        Path bgmDir = mediaBgmDir();
        Path filePath = bgmDir.resolve(emotion).resolve(file);

        if (Files.isRegularFile(filePath)) {
            return filePath;
        }

        log.debug("BGM file not found: {}", filePath);
        return null;
    }

    private Path mediaBgmDir() {
        Path bgmPath = mediaDir.resolve("bgm");
        if (Files.isDirectory(bgmPath)) {
            return bgmPath;
        }
        // Fallback to /app/media/bgm if custom media-dir is not set
        return Path.of("/app/media/bgm");
    }

    /**
     * Get duration of audio file in seconds (simplified: returns 0 if unable to determine)
     * For production, consider using a library like jaudiotagger or mediautil
     */
    private long getDurationSec(Path file) {
        // Placeholder: return 0
        // In production, parse MP3 metadata or use FFmpeg/mediainfo
        return 0L;
    }
}
