package com.wagglebot.settings;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.HashMap;
import java.util.Map;

/**
 * config/pipeline.json 읽기/쓰기 서비스.
 * Python ai_worker/dashboard_worker와 동일 볼륨 공유 — atomic rename으로 안전 쓰기.
 * Python의 5초 캐시가 새 값을 픽업.
 */
@Service
@Slf4j
public class SettingsService {

    private final Path configDir;
    private static final ObjectMapper MAPPER = new ObjectMapper();
    private static final TypeReference<Map<String, Object>> MAP_REF = new TypeReference<>() {};

    private static final Map<String, Object> DEFAULTS = Map.of(
        "llm_model", "haiku",
        "llm_model_overrides", "{}",
        "tts_engine", "fish-speech",
        "tts_voice", "yura",
        "auto_approve_threshold", 80,
        "max_chars_per_line", 20,
        "max_body_items", 23,
        "llm_backend", "cli"
    );

    public SettingsService(@Value("${app.config-dir:/app/config}") String configDirStr) {
        this.configDir = Path.of(configDirStr);
    }

    public Map<String, Object> loadPipelineConfig() {
        Path path = configDir.resolve("pipeline.json");
        Map<String, Object> merged = new HashMap<>(DEFAULTS);
        if (Files.exists(path)) {
            try {
                String content = Files.readString(path, StandardCharsets.UTF_8);
                Map<String, Object> loaded = MAPPER.readValue(content, MAP_REF);
                merged.putAll(loaded);
            } catch (IOException e) {
                log.warn("pipeline.json 로드 실패, 기본값 사용: {}", e.getMessage());
            }
        }
        return merged;
    }

    public void savePipelineConfig(Map<String, Object> config) throws IOException {
        // 부분 저장이 다른 키(llm_backend, llm_model_overrides 등)를 지우지 않도록 기존 파일과 병합
        Path path = configDir.resolve("pipeline.json");
        Map<String, Object> merged = new HashMap<>();
        if (Files.exists(path)) {
            try {
                merged.putAll(MAPPER.readValue(Files.readString(path, StandardCharsets.UTF_8), MAP_REF));
            } catch (IOException e) {
                log.warn("pipeline.json 병합 로드 실패, 덮어쓰기로 진행: {}", e.getMessage());
            }
        }
        merged.putAll(config);
        atomicWrite(path, MAPPER.writeValueAsString(merged));
    }

    public Map<String, Object> loadCredentialsConfig() {
        Path path = configDir.resolve("credentials.json");
        if (!Files.exists(path)) return new HashMap<>();
        try {
            return MAPPER.readValue(Files.readString(path, StandardCharsets.UTF_8), MAP_REF);
        } catch (IOException e) {
            log.warn("credentials.json 로드 실패: {}", e.getMessage());
            return new HashMap<>();
        }
    }

    public void saveCredentialsConfig(Map<String, Object> creds) throws IOException {
        // 기존 시크릿과 병합 + 마스킹("***")/빈 값은 무시(실제 키 보존)
        Map<String, Object> merged = loadCredentialsConfig();
        creds.forEach((k, v) -> {
            if (v instanceof String s && (s.isBlank() || s.contains("***"))) return;
            merged.put(k, v);
        });
        atomicWrite(configDir.resolve("credentials.json"), MAPPER.writeValueAsString(merged));
    }

    private void atomicWrite(Path target, String content) throws IOException {
        Path tmp = target.resolveSibling(target.getFileName() + ".tmp");
        Files.writeString(tmp, content, StandardCharsets.UTF_8);
        try {
            Files.move(tmp, target, StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING);
        } catch (AtomicMoveNotSupportedException e) {
            Files.move(tmp, target, StandardCopyOption.REPLACE_EXISTING);
        }
    }
}
