package com.wagglebot.settings;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

@Service
@Slf4j
public class VoiceCatalogService {

    private final Path configDir;
    private final SettingsService settingsService;
    private static final ObjectMapper MAPPER = new ObjectMapper();

    @Autowired
    public VoiceCatalogService(
        @Value("${app.config-dir:/app/config}") String configDirStr,
        SettingsService settingsService
    ) {
        this.configDir = Path.of(configDirStr);
        this.settingsService = settingsService;
    }

    /**
     * config/voices.json 읽기. 없으면 빈 리스트 반환.
     * 각 항목에 sampleUrl 합성: /api/media/voices/{file}
     */
    public List<Map<String, Object>> loadVoices() {
        Path path = configDir.resolve("voices.json");
        if (!Files.exists(path)) return new ArrayList<>();
        try {
            String json = Files.readString(path, StandardCharsets.UTF_8);
            Map<String, Object> root = MAPPER.readValue(json, new TypeReference<Map<String, Object>>() {});
            @SuppressWarnings("unchecked")
            List<Map<String, Object>> voices = (List<Map<String, Object>>) root.getOrDefault("voices", new ArrayList<>());
            List<Map<String, Object>> result = new ArrayList<>();
            // assets/voices is mounted at /app/media/voices in backend
            Path voicesDir = mediaVoicesDir();
            for (Map<String, Object> voice : voices) {
                Map<String, Object> entry = new LinkedHashMap<>(voice);
                String key = voice.get("key") != null ? voice.get("key").toString() : "";
                String sample = resolveSampleUrl(voicesDir, key, voice.get("file"));
                if (sample != null) {
                    entry.put("sampleUrl", sample);
                    entry.put("hasSample", true);
                } else {
                    entry.put("hasSample", false);
                }
                result.add(entry);
            }
            return result;
        } catch (IOException e) {
            log.warn("voices.json 로드 실패: {}", e.getMessage());
            return new ArrayList<>();
        }
    }

    /**
     * pipeline.json의 tts_voice 값 (기본값: "yura")
     */
    public String getDefaultVoice() {
        Map<String, Object> cfg = settingsService.loadPipelineConfig();
        Object val = cfg.getOrDefault("tts_voice", "yura");
        return val != null ? val.toString() : "yura";
    }

    /**
     * config/prompt_presets.json 읽기. 없으면 빈 리스트 반환.
     */
    public List<Map<String, String>> getPromptPresets() {
        Path path = configDir.resolve("prompt_presets.json");
        if (!Files.exists(path)) return new ArrayList<>();
        try {
            String json = Files.readString(path, StandardCharsets.UTF_8);
            Map<String, Object> root = MAPPER.readValue(json, new TypeReference<Map<String, Object>>() {});
            @SuppressWarnings("unchecked")
            List<Map<String, String>> presets = (List<Map<String, String>>) root.getOrDefault("presets", new ArrayList<>());
            return presets;
        } catch (IOException e) {
            log.warn("prompt_presets.json 로드 실패: {}", e.getMessage());
            return new ArrayList<>();
        }
    }

    /**
     * voice 키 유효성 검사. null은 전역 기본값 사용을 의미하므로 허용.
     */
    public boolean isValidVoiceKey(String key) {
        if (key == null) return true;
        List<Map<String, Object>> voices = loadVoices();
        return voices.stream().anyMatch(v -> key.equals(v.get("key")));
    }

    private Path mediaVoicesDir() {
        // Prefer mounted media/voices (docker); fall back to assets/voices next to config
        Path media = Path.of("/app/media/voices");
        if (Files.isDirectory(media)) return media;
        Path assets = configDir.resolveSibling("assets").resolve("voices");
        if (Files.isDirectory(assets)) return assets;
        return media;
    }

    /**
     * Prefer ref wav if present; else fuzzy-match voice_preview_*.mp3 by key.
     * Returns a key-based TTS sample URL (avoids spaces/commas in preview filenames).
     */
    private String resolveSampleUrl(Path voicesDir, String key, Object fileObj) {
        if (key == null || key.isBlank()) return null;
        if (resolveSampleFile(voicesDir, key, fileObj) == null) return null;
        return "/api/tts/voices/" + key + "/sample";
    }

    /** Resolve on-disk sample file for a voice key, or null if none. */
    public Path resolveSampleFile(Path voicesDir, String key, Object fileObj) {
        if (voicesDir == null) voicesDir = mediaVoicesDir();
        if (fileObj != null) {
            Path wav = voicesDir.resolve(fileObj.toString());
            if (Files.isRegularFile(wav)) return wav;
        }
        if (key == null || key.isBlank() || !Files.isDirectory(voicesDir)) return null;
        String needle = key.toLowerCase().replace("_", " ").replace("-", " ");
        try (var stream = Files.list(voicesDir)) {
            return stream
                .filter(p -> {
                    String n = p.getFileName().toString().toLowerCase();
                    return n.startsWith("voice_preview_") && n.endsWith(".mp3");
                })
                .filter(p -> {
                    String n = p.getFileName().toString().toLowerCase()
                        .replace("voice_preview_", "")
                        .replace(".mp3", "");
                    String norm = n.replace("-", " ");
                    return norm.equals(needle) || norm.startsWith(needle + " ") || norm.contains(needle);
                })
                .findFirst()
                .orElse(null);
        } catch (IOException e) {
            log.debug("voice preview scan failed: {}", e.getMessage());
            return null;
        }
    }

    public Path resolveSampleFile(String key) {
        if (key == null || key.isBlank()) return null;
        Path voicesDir = mediaVoicesDir();
        Object fileObj = null;
        for (Map<String, Object> v : loadVoicesRaw()) {
            if (key.equals(String.valueOf(v.get("key")))) {
                fileObj = v.get("file");
                break;
            }
        }
        return resolveSampleFile(voicesDir, key, fileObj);
    }

    /** Load voices.json entries without sampleUrl enrichment (avoids recursion). */
    private List<Map<String, Object>> loadVoicesRaw() {
        Path path = configDir.resolve("voices.json");
        if (!Files.exists(path)) return new ArrayList<>();
        try {
            String json = Files.readString(path, StandardCharsets.UTF_8);
            Map<String, Object> root = MAPPER.readValue(json, new TypeReference<Map<String, Object>>() {});
            @SuppressWarnings("unchecked")
            List<Map<String, Object>> voices = (List<Map<String, Object>>) root.getOrDefault("voices", new ArrayList<>());
            return voices;
        } catch (IOException e) {
            log.warn("voices.json 로드 실패: {}", e.getMessage());
            return new ArrayList<>();
        }
    }
}
