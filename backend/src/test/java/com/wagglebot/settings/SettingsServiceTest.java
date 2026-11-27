package com.wagglebot.settings;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;

class SettingsServiceTest {

    @TempDir Path tmp;

    private String savedVoice(SettingsService s, Object voice) throws Exception {
        s.savePipelineConfig(Map.of("tts_voice", voice));
        Map<?, ?> saved = new ObjectMapper().readValue(Files.readString(tmp.resolve("pipeline.json")), Map.class);
        return String.valueOf(saved.get("tts_voice"));
    }

    @Test
    void missingPipelineJsonDefaultsToAutoVoice() {
        assertEquals("default", new SettingsService(tmp.toString()).loadPipelineConfig().get("tts_voice"));
    }

    @Test
    void saveKeepsAutoPresetAndLegacyVoiceWithoutPinningF1() throws Exception {
        SettingsService s = new SettingsService(tmp.toString());
        assertEquals("default", savedVoice(s, "default"));
        assertEquals("default", savedVoice(s, "DEFAULT"));
        assertEquals("default", savedVoice(s, ""));
        assertEquals("M3", savedVoice(s, "M3"));          // 명시 프리셋은 그 프리셋으로 고정
        assertEquals("yura", savedVoice(s, "yura"));       // 구 키도 조용히 바뀌지 않는다
    }

    @Test
    void saveWithoutTtsVoiceKeepsExistingValue() throws Exception {
        Files.writeString(tmp.resolve("pipeline.json"), "{\"tts_voice\":\"F4\"}");
        SettingsService s = new SettingsService(tmp.toString());
        s.savePipelineConfig(Map.of("llm_model", "sonnet"));
        assertEquals("F4", s.loadPipelineConfig().get("tts_voice"));
    }
}
