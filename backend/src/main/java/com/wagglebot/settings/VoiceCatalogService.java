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
            for (Map<String, Object> voice : voices) {
                Map<String, Object> entry = new LinkedHashMap<>(voice);
                Object file = voice.get("file");
                if (file != null) {
                    entry.put("sampleUrl", "/api/media/voices/" + file);
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
}
