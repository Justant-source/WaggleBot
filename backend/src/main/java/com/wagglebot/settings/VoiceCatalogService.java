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
import java.util.regex.Pattern;

@Service
@Slf4j
public class VoiceCatalogService {

    private static final String DEFAULT_PRESET = "F1";
    private static final Pattern PRESET_KEY = Pattern.compile("^[MFmf][1-5]$");

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
     * config/voices.json(v4: Supertonic 프리셋 M1~M5/F1~F5) 읽기. 없으면 빈 리스트 반환.
     * 미리 생성한 샘플(voice_preview_{KEY}.mp3)이 있으면 sampleUrl=/api/tts/voices/{key}/sample 합성.
     */
    public List<Map<String, Object>> loadVoices() {
        List<Map<String, Object>> result = new ArrayList<>();
        Path voicesDir = mediaVoicesDir();
        for (Map<String, Object> voice : loadVoicesRaw()) {
            Map<String, Object> entry = new LinkedHashMap<>(voice);
            String key = voice.get("key") != null ? voice.get("key").toString() : "";
            if (findPreviewFile(voicesDir, key) != null) {
                entry.put("sampleUrl", "/api/tts/voices/" + key + "/sample");
                entry.put("hasSample", true);
            } else {
                entry.put("hasSample", false);
            }
            result.add(entry);
        }
        return result;
    }

    /**
     * pipeline.json의 tts_voice 값. 프리셋이 아닌 구 키(예: yura)는 UI 표시용으로 "F1"을 반환한다
     * (실제 합성 시에는 워커 voice_resolver가 성별 보존 매핑).
     */
    public String getDefaultVoice() {
        Map<String, Object> cfg = settingsService.loadPipelineConfig();
        Object val = cfg.get("tts_voice");
        String key = val != null ? val.toString().trim() : "";
        return isPresetKey(key) ? key.toUpperCase() : DEFAULT_PRESET;
    }

    private boolean isPresetKey(String key) {
        return key != null && PRESET_KEY.matcher(key).matches();
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
     * voice 키 유효성 검사. null은 전역 기본값 사용을 의미하므로 허용. 프리셋 키(대소문자 무관)만 허용.
     */
    public boolean isValidVoiceKey(String key) {
        if (key == null) return true;
        return loadVoicesRaw().stream().anyMatch(v -> key.equalsIgnoreCase(String.valueOf(v.get("key"))));
    }

    private Path mediaVoicesDir() {
        // Prefer mounted media/voices (docker); fall back to assets/voices next to config
        Path media = Path.of("/app/media/voices");
        if (Files.isDirectory(media)) return media;
        Path assets = configDir.resolveSibling("assets").resolve("voices");
        if (Files.isDirectory(assets)) return assets;
        return media;
    }

    /** voice_preview_{KEY}.mp3 (대소문자 무관 정확 일치). 없으면 null. 경로 조작 방지를 위해 프리셋 키 형식만 허용. */
    private Path findPreviewFile(Path voicesDir, String key) {
        if (!isPresetKey(key) || voicesDir == null || !Files.isDirectory(voicesDir)) return null;
        for (String name : new String[] {"voice_preview_" + key + ".mp3", "voice_preview_" + key.toUpperCase() + ".mp3"}) {
            Path p = voicesDir.resolve(name);
            if (Files.isRegularFile(p)) return p;
        }
        return null;
    }

    /** Resolve on-disk sample file for a voice key, or null if none. */
    public Path resolveSampleFile(String key) {
        if (key == null || key.isBlank()) return null;
        return findPreviewFile(mediaVoicesDir(), key);
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
