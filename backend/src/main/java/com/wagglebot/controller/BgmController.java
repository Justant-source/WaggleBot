package com.wagglebot.controller;

import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import com.fasterxml.jackson.databind.JsonNode;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Stream;

/**
 * BGM 카탈로그 — assets/media/bgm/<emotion>/*.mp3 를 훑어 목록으로 돌려준다.
 *
 * 미리듣기는 별도 엔드포인트를 두지 않는다. 파일이 이미 /app/media 아래에 있어
 * 기존 MediaController가 /api/media/bgm/<emotion>/<file> 로 그대로 서빙한다.
 */
@RestController
@RequestMapping("/api/bgm")
@Slf4j
public class BgmController {

    /** hook_emotion 과 같은 표시 순서 — 강한 감정부터. */
    private static final List<String> EMOTION_ORDER =
        List.of("shock", "anger", "tension", "sad", "hype");

    private static final Map<String, String> EMOTION_LABEL = Map.of(
        "shock", "충격",
        "anger", "분노",
        "tension", "긴장",
        "sad", "슬픔",
        "hype", "활기"
    );

    private final Path mediaDir;
    private final Path settingsPath;

    public BgmController(
        @Value("${app.media-dir:/app/media}") String mediaDirStr,
        @Value("${app.renderer-settings:/app/renderer/settings.yaml}") String settingsStr
    ) {
        this.mediaDir = Path.of(mediaDirStr);
        this.settingsPath = Path.of(settingsStr);
    }

    /**
     * 배경음악 전역 사용 여부. false 면 어떤 렌더에도 BGM 을 넣지 않는다.
     * 고르는 기능(카탈로그·잡별 bgmTrack)은 그대로 살아 있어 값만 되돌리면 복귀한다.
     */
    @PutMapping("/settings")
    public Map<String, Object> putSettings(@RequestBody JsonNode body) {
        JsonNode en = body.get("enabled");
        if (en == null || !en.isBoolean()) {
            throw new IllegalArgumentException("enabled(boolean) 가 필요합니다");
        }
        writeEnabled(en.asBoolean());
        return Map.of("enabled", readEnabled());
    }

    @GetMapping("/tracks")
    public Map<String, Object> listTracks() {
        Path bgmRoot = mediaDir.resolve("bgm");
        List<Map<String, Object>> tracks = new ArrayList<>();
        if (!Files.isDirectory(bgmRoot)) {
            log.warn("[bgm] 디렉토리 없음: {}", bgmRoot);
            return Map.of("tracks", tracks, "enabled", readEnabled());
        }
        for (String emotion : EMOTION_ORDER) {
            Path dir = bgmRoot.resolve(emotion);
            if (!Files.isDirectory(dir)) continue;
            try (Stream<Path> files = Files.list(dir)) {
                files.filter(Files::isRegularFile)
                    .filter(p -> p.getFileName().toString().toLowerCase().endsWith(".mp3"))
                    .sorted(Comparator.comparing(p -> p.getFileName().toString()))
                    .forEach(p -> {
                        String file = p.getFileName().toString();
                        Map<String, Object> entry = new LinkedHashMap<>();
                        entry.put("emotion", emotion);
                        entry.put("emotionLabel", EMOTION_LABEL.getOrDefault(emotion, emotion));
                        entry.put("file", file);
                        // 선택값이자 재생 경로 — 그대로 variant_config.bgm_track 으로 저장된다
                        entry.put("path", "/api/media/bgm/" + emotion + "/" + file);
                        tracks.add(entry);
                    });
            } catch (IOException e) {
                log.warn("[bgm] 목록 실패: {}", dir, e);
            }
        }
        return Map.of("tracks", tracks, "enabled", readEnabled());
    }

    // ── 전역 스위치 입출력 ──────────────────────────────────────────────
    // settings.yaml 을 YAML 파서로 로드→덤프하면 다른 섹션의 주석이 날아가므로
    // bgm.enabled 줄만 문자열로 갈아 끼운다.

    private boolean readEnabled() {
        try {
            for (String line : Files.readString(settingsPath, java.nio.charset.StandardCharsets.UTF_8).split("\n")) {
                if (line.trim().startsWith("enabled:")) {
                    return !line.contains("false");
                }
            }
        } catch (IOException e) {
            log.warn("[bgm] 설정을 읽지 못했습니다: {}", settingsPath, e);
        }
        return true;
    }

    private void writeEnabled(boolean enabled) {
        try {
            String src = Files.readString(settingsPath, java.nio.charset.StandardCharsets.UTF_8);
            String[] lines = src.split("\n", -1);
            boolean inBgm = false, done = false;
            for (int i = 0; i < lines.length; i++) {
                if (lines[i].startsWith("bgm:")) { inBgm = true; continue; }
                if (inBgm) {
                    if (lines[i].trim().startsWith("enabled:")) {
                        lines[i] = "  enabled: " + enabled;
                        done = true;
                        break;
                    }
                    if (!lines[i].isBlank() && !lines[i].startsWith(" ")) break;
                }
            }
            if (!done) {
                throw new IllegalStateException("settings.yaml 에서 bgm.enabled 를 찾지 못했습니다");
            }
            Files.writeString(settingsPath, String.join("\n", lines), java.nio.charset.StandardCharsets.UTF_8);
            log.info("[bgm] 전역 사용 여부 변경: {}", enabled);
        } catch (IOException e) {
            throw new IllegalStateException("settings.yaml 저장 실패: " + e.getMessage());
        }
    }
}
