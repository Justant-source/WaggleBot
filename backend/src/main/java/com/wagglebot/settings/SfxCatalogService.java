package com.wagglebot.settings;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.dataformat.yaml.YAMLFactory;
import com.fasterxml.jackson.dataformat.yaml.YAMLGenerator;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.*;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.stream.Collectors;
import java.util.stream.Stream;

@Service
@Slf4j
public class SfxCatalogService {

    private final Path configDir;
    private final Path mediaDir;
    private static final ObjectMapper YAML_MAPPER = new ObjectMapper(
        new YAMLFactory().disable(YAMLGenerator.Feature.WRITE_DOC_START_MARKER)
    );

    @Autowired
    public SfxCatalogService(
        @Value("${app.config-dir:/app/config}") String configDirStr,
        @Value("${app.media-dir:/app/media}") String mediaDirStr
    ) {
        this.configDir = Path.of(configDirStr);
        this.mediaDir = Path.of(mediaDirStr);
    }

    /**
     * GET /api/sfx/mapping — 현재 설정 + 라이브러리 반환
     */
    public Map<String, Object> loadSfxMapping() {
        Map<String, Object> result = new LinkedHashMap<>();

        // 1. sfx.active 섹션 읽기
        Map<String, Object> sfxActive = loadSfxActive();

        // 2. events 리스트로 변환 (순서 유지)
        List<Map<String, Object>> events = new ArrayList<>();
        if (sfxActive != null) {
            sfxActive.forEach((key, value) -> {
                if (value instanceof Map) {
                    @SuppressWarnings("unchecked")
                    Map<String, Object> evt = (Map<String, Object>) value;
                    Map<String, Object> eventEntry = new LinkedHashMap<>();
                    eventEntry.put("key", key);
                    eventEntry.putAll(evt);
                    events.add(eventEntry);
                }
            });
        }

        // maxPerVideo와 minGapSec은 settings.yaml의 sfx.max_per_video / min_gap_sec에서 읽기
        int maxPerVideo = 18;
        Map<String, Object> sfxConfig = loadSfxConfig();
        if (sfxConfig.containsKey("max_per_video")) {
            Object val = sfxConfig.get("max_per_video");
            if (val instanceof Number) {
                maxPerVideo = ((Number) val).intValue();
            }
        }

        result.put("events", events);
        result.put("maxPerVideo", maxPerVideo);

        // 3. 라이브러리 스캔 (현재 파일 + 카테고리)
        List<Map<String, Object>> library = scanLibrary();
        result.put("library", library);

        return result;
    }

    /**
     * PUT /api/sfx/mapping — 설정 업데이트 + 검증 + 저장
     * @param request { "events": [...], "maxPerVideo": 40 }
     */
    public Map<String, Object> updateSfxMapping(Map<String, Object> request) throws IOException {
        // 1. 입력 검증
        @SuppressWarnings("unchecked")
        List<Map<String, Object>> events = (List<Map<String, Object>>) request.get("events");
        Object maxPerVideoObj = request.get("maxPerVideo");

        if (events == null) {
            throw new IllegalArgumentException("events 필드 필수");
        }

        int maxPerVideo = 18;
        if (maxPerVideoObj != null) {
            if (maxPerVideoObj instanceof Number) {
                maxPerVideo = ((Number) maxPerVideoObj).intValue();
            } else {
                throw new IllegalArgumentException("maxPerVideo는 정수여야 함");
            }
        }

        // 2. 각 이벤트 검증
        for (Map<String, Object> event : events) {
            validateEvent(event);
        }

        // 3. settings.yaml 업데이트 (주석 보존)
        updateSettingsYaml(events, maxPerVideo);

        // 4. 갱신된 내용 반환
        return loadSfxMapping();
    }

    /**
     * 이벤트 검증
     */
    private void validateEvent(Map<String, Object> event) {
        String key = (String) event.get("key");
        String file = (String) event.get("file");
        Object volumeObj = event.get("volume");
        Object offsetObj = event.get("offset");

        // key 검증: [a-z_]{2,32}
        if (key == null || !key.matches("[a-z_]{2,32}")) {
            throw new IllegalArgumentException("key 형식 오류: " + key);
        }

        // file 검증: ".." 금지 + 실제 파일 존재
        if (file == null || file.contains("..")) {
            throw new IllegalArgumentException("file 경로 오류: " + file);
        }

        Path filePath = mediaDir.resolve("sfx").resolve(file);
        if (!Files.isRegularFile(filePath)) {
            throw new IllegalArgumentException("파일 없음: " + file);
        }

        // volume 검증: 0~1.5
        double volume = 0.8;
        if (volumeObj instanceof Number) {
            volume = ((Number) volumeObj).doubleValue();
        }
        if (volume < 0 || volume > 1.5) {
            throw new IllegalArgumentException("volume 범위: 0~1.5");
        }

        // offset 검증: -5~10
        double offset = 0.0;
        if (offsetObj instanceof Number) {
            offset = ((Number) offsetObj).doubleValue();
        }
        if (offset < -5 || offset > 10) {
            throw new IllegalArgumentException("offset 범위: -5~10");
        }
    }

    /**
     * settings.yaml 의 sfx.active 섹션 업데이트 (주석 보존)
     */
    private void updateSettingsYaml(List<Map<String, Object>> events, int maxPerVideo) throws IOException {
        Path yamlPath = configDir.resolve("renderer-settings.yaml");
        if (!Files.exists(yamlPath)) {
            log.warn("settings.yaml 찾을 수 없음: {}", yamlPath);
            throw new IOException("settings.yaml 찾을 수 없음");
        }

        String yamlContent = Files.readString(yamlPath, StandardCharsets.UTF_8);

        // sfx.active 블록을 문자열로 생성
        String sfxActiveBlock = buildSfxActiveYaml(events, maxPerVideo);

        // 기존 sfx.active ~ (다음 섹션 직전까지) 정규표현식으로 교체
        // 매우 신중하게: 들여쓰기, 주석 등 보존
        String updatedYaml = replaceSfxActiveBlock(yamlContent, sfxActiveBlock);

        // 원자적 쓰기
        atomicWrite(yamlPath, updatedYaml);
        log.info("settings.yaml sfx.active 업데이트 완료");
    }

    /**
     * sfx.active YAML 블록 문자열 생성
     */
    private String buildSfxActiveYaml(List<Map<String, Object>> events, int maxPerVideo) {
        StringBuilder sb = new StringBuilder();
        sb.append("  active:\n");

        for (Map<String, Object> event : events) {
            String key = (String) event.get("key");
            String file = (String) event.get("file");
            double volume = event.get("volume") instanceof Number ?
                ((Number) event.get("volume")).doubleValue() : 0.8;
            double offset = event.get("offset") instanceof Number ?
                ((Number) event.get("offset")).doubleValue() : 0.0;

            sb.append("    ").append(key).append(":\n");
            sb.append("      file: ").append(file).append("\n");
            sb.append("      volume: ").append(volume).append("\n");
            sb.append("      offset: ").append(offset).append("\n");
        }

        sb.append("  max_per_video: ").append(maxPerVideo).append("\n");

        return sb.toString();
    }

    /**
     * YAML에서 sfx 섹션 업데이트 (정규표현식으로 sfx.active와 max_per_video 교체)
     * 다른 섹션은 절대 건드리지 않음
     */
    private String replaceSfxActiveBlock(String yamlContent, String newSfxBlock) {
        // sfx: 섹션을 찾아서 다음 톱레벨 섹션(# ── 주석 또는 ^[a-z])까지 교체
        // Pattern: ^sfx:\n(.*?)(?=^[a-z]|^#|$)
        Pattern pattern = Pattern.compile(
            "^sfx:\\n(.*?)(?=^(?:thumbnail|tone_v2|quality|codec|fps|audio):|^# ──|\\Z)",
            Pattern.MULTILINE | Pattern.DOTALL
        );

        Matcher matcher = pattern.matcher(yamlContent);
        if (matcher.find()) {
            String beforeSfx = yamlContent.substring(0, matcher.start());
            String afterSfx = yamlContent.substring(matcher.end());
            return beforeSfx + "sfx:\n" + newSfxBlock + afterSfx;
        } else {
            log.warn("sfx 섹션을 찾을 수 없음, 파일 끝에 추가");
            return yamlContent + "\nsfx:\n" + newSfxBlock;
        }
    }

    /**
     * 원자적 쓰기
     */
    private void atomicWrite(Path target, String content) throws IOException {
        Path tmp = target.resolveSibling(target.getFileName() + ".tmp");
        Files.writeString(tmp, content, StandardCharsets.UTF_8);
        try {
            Files.move(tmp, target, java.nio.file.StandardCopyOption.ATOMIC_MOVE,
                java.nio.file.StandardCopyOption.REPLACE_EXISTING);
        } catch (java.nio.file.AtomicMoveNotSupportedException e) {
            Files.move(tmp, target, java.nio.file.StandardCopyOption.REPLACE_EXISTING);
        }
    }

    /**
     * settings.yaml에서 sfx.active 섹션 읽기
     */
    private Map<String, Object> loadSfxActive() {
        Map<String, Object> sfxConfig = loadSfxConfig();
        @SuppressWarnings("unchecked")
        Map<String, Object> active = (Map<String, Object>) sfxConfig.get("active");
        return active != null ? active : new LinkedHashMap<>();
    }

    /**
     * settings.yaml에서 sfx 섹션 전체 읽기
     */
    private Map<String, Object> loadSfxConfig() {
        Path yamlPath = configDir.resolve("renderer-settings.yaml");
        if (!Files.exists(yamlPath)) {
            log.warn("settings.yaml 찾을 수 없음: {}", yamlPath);
            return new LinkedHashMap<>();
        }

        try {
            String content = Files.readString(yamlPath, StandardCharsets.UTF_8);
            @SuppressWarnings("unchecked")
            Map<String, Object> root = YAML_MAPPER.readValue(content, Map.class);
            @SuppressWarnings("unchecked")
            Map<String, Object> sfx = (Map<String, Object>) root.getOrDefault("sfx", new LinkedHashMap<>());
            return sfx;
        } catch (IOException e) {
            log.error("settings.yaml 로드 실패: {}", e.getMessage());
            return new LinkedHashMap<>();
        }
    }

    /**
     * 라이브러리 스캔: 현재 파일 + _library 카테고리별 목록
     */
    private List<Map<String, Object>> scanLibrary() {
        List<Map<String, Object>> library = new ArrayList<>();
        Path sfxDir = mediaDir.resolve("sfx");
        Path libraryDir = sfxDir.resolve("_library");

        // 1. 현재 파일 (sfx/*.wav)
        Map<String, Object> currentFiles = new LinkedHashMap<>();
        currentFiles.put("category", "current");
        List<Map<String, Object>> currentList = new ArrayList<>();

        try (Stream<Path> stream = Files.list(sfxDir)) {
            stream
                .filter(p -> Files.isRegularFile(p) && p.toString().endsWith(".wav"))
                .sorted()
                .forEach(p -> {
                    Map<String, Object> file = new LinkedHashMap<>();
                    file.put("name", p.getFileName().toString());
                    file.put("path", p.getFileName().toString());
                    currentList.add(file);
                });
        } catch (IOException e) {
            log.debug("sfx 디렉토리 스캔 실패: {}", e.getMessage());
        }

        if (!currentList.isEmpty()) {
            currentFiles.put("files", currentList);
            library.add(currentFiles);
        }

        // 2. _library 카테고리별 스캔
        if (Files.isDirectory(libraryDir)) {
            try (Stream<Path> stream = Files.list(libraryDir)) {
                stream
                    .filter(Files::isDirectory)
                    .sorted(Comparator.comparing(p -> p.getFileName().toString()))
                    .forEach(categoryDir -> {
                        String category = categoryDir.getFileName().toString();
                        Map<String, Object> categoryEntry = new LinkedHashMap<>();
                        categoryEntry.put("category", category);

                        List<Map<String, Object>> filesList = new ArrayList<>();
                        try (Stream<Path> fileStream = Files.list(categoryDir)) {
                            fileStream
                                .filter(p -> Files.isRegularFile(p) && p.toString().endsWith(".wav"))
                                .sorted(Comparator.comparing(p -> p.getFileName().toString()))
                                .forEach(p -> {
                                    Map<String, Object> file = new LinkedHashMap<>();
                                    file.put("name", p.getFileName().toString());
                                    file.put("path", "_library/" + category + "/" + p.getFileName().toString());
                                    filesList.add(file);
                                });
                        } catch (IOException e) {
                            log.debug("카테고리 스캔 실패 {}: {}", category, e.getMessage());
                        }

                        categoryEntry.put("files", filesList);
                        library.add(categoryEntry);
                    });
            } catch (IOException e) {
                log.debug("_library 스캔 실패: {}", e.getMessage());
            }
        }

        return library;
    }
}
