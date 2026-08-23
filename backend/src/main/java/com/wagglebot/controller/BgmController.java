package com.wagglebot.controller;

import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.web.bind.annotation.GetMapping;
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

    public BgmController(@Value("${app.media-dir:/app/media}") String mediaDirStr) {
        this.mediaDir = Path.of(mediaDirStr);
    }

    @GetMapping("/tracks")
    public Map<String, Object> listTracks() {
        Path bgmRoot = mediaDir.resolve("bgm");
        List<Map<String, Object>> tracks = new ArrayList<>();
        if (!Files.isDirectory(bgmRoot)) {
            log.warn("[bgm] 디렉토리 없음: {}", bgmRoot);
            return Map.of("tracks", tracks);
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
        return Map.of("tracks", tracks);
    }
}
