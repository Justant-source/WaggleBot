package com.wagglebot.settings;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class VoiceCatalogServiceTest {

    @TempDir Path tmp;

    private VoiceCatalogService service(String ttsVoice) throws Exception {
        Path config = tmp.resolve("config");
        Files.createDirectories(config);
        Files.copy(Path.of("../config/voices.json"), config.resolve("voices.json"), java.nio.file.StandardCopyOption.REPLACE_EXISTING);
        Path voices = tmp.resolve("assets/voices");
        Files.createDirectories(voices);
        Files.write(voices.resolve("voice_preview_M1.mp3"), new byte[] {1, 2, 3});
        SettingsService settings = mock(SettingsService.class);
        when(settings.loadPipelineConfig()).thenReturn(Map.of("tts_voice", ttsVoice));
        return new VoiceCatalogService(config.toString(), settings);
    }

    @Test
    void catalogReturnsTenPresetsWithSampleOnlyWhereFileExists() throws Exception {
        List<Map<String, Object>> voices = service("F1").loadVoices();
        assertEquals(10, voices.size());
        Map<String, Object> m1 = voices.get(0);
        assertEquals("M1", m1.get("key"));
        assertEquals(true, m1.get("hasSample"));
        assertEquals("/api/tts/voices/M1/sample", m1.get("sampleUrl"));
        assertEquals(false, voices.get(1).get("hasSample"));
    }

    @Test
    void defaultVoiceKeepsAutoPresetAndLegacyKeys() throws Exception {
        assertEquals("default", service("default").getDefaultVoice());   // 자동(글별 랜덤)은 F1로 바뀌지 않는다
        assertEquals("default", service("").getDefaultVoice());
        assertEquals("M3", service("m3").getDefaultVoice());
        assertEquals("seohyeon_ref", service("seohyeon_ref").getDefaultVoice());   // 구 키는 보존
    }

    @Test
    void voiceKeyValidationAcceptsPresetsOnly() throws Exception {
        VoiceCatalogService s = service("F1");
        assertTrue(s.isValidVoiceKey(null));
        assertTrue(s.isValidVoiceKey("f2"));
        assertFalse(s.isValidVoiceKey("yura"));
    }

    @Test
    void resolveSampleFileRejectsTraversalAndLegacyKeys() throws Exception {
        VoiceCatalogService s = service("F1");
        assertNotNull(s.resolveSampleFile("M1"));
        assertNull(s.resolveSampleFile("../M1"));
        assertNull(s.resolveSampleFile("yura"));
    }
}
