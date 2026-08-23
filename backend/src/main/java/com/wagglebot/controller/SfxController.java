package com.wagglebot.controller;

import com.fasterxml.jackson.databind.JsonNode;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.regex.Pattern;
import java.util.stream.Stream;

/**
 * 효과음 매핑 API — 어드민이 지점별 소리를 고를 수 있게 연다.
 *
 * <p>권위본은 렌더러 설정(`worker/ai_worker/renderer/settings.yaml`)의 {@code sfx} 블록이다.
 * YAML 라이브러리로 로드→덤프하면 다른 섹션의 주석이 전부 날아가므로,
 * {@code sfx:} 블록만 문자열로 잘라내고 새로 쓴 블록을 끼워 넣는다.
 *
 * <p>음원 경로는 `assets/media/sfx/` 기준 상대경로다. 렌더러의
 * {@code _resolve_sfx_path} 가 {@code MEDIA_DIR/sfx/<값>} 으로 풀기 때문에
 * {@code _library/click/x.wav} 같은 하위 경로도 그대로 동작한다.
 */
@RestController
@RequestMapping("/api/sfx")
@Slf4j
public class SfxController {

    /** 이벤트 키 — 소문자·밑줄만. 임의 키가 설정에 들어가는 것을 막는다. */
    private static final Pattern KEY_RE = Pattern.compile("[a-z_]{2,32}");
    /** 음원 경로 — sfx 디렉토리 안의 wav 만. 경로 탈출 차단. */
    private static final Pattern FILE_RE =
        Pattern.compile("(_library/[A-Za-z0-9_-]+/|_candidates/[A-Za-z0-9_-]+/)?[A-Za-z0-9_.-]+\\.wav");

    private final Path mediaDir;
    private final Path settingsPath;

    public SfxController(
        @Value("${app.media-dir:/app/media}") String mediaDirStr,
        @Value("${app.renderer-settings:/app/renderer/settings.yaml}") String settingsStr
    ) {
        this.mediaDir = Path.of(mediaDirStr);
        this.settingsPath = Path.of(settingsStr);
    }

    @GetMapping("/mapping")
    public Map<String, Object> getMapping() {
        Map<String, Object> out = new LinkedHashMap<>();
        SfxBlock block = readBlock();
        out.put("events", block.events);
        out.put("maxPerVideo", block.maxPerVideo);
        out.put("library", listLibrary());
        return out;
    }

    @PutMapping("/mapping")
    public Map<String, Object> putMapping(@RequestBody JsonNode body) {
        JsonNode evNode = body.get("events");
        if (evNode == null || !evNode.isArray() || evNode.isEmpty()) {
            throw bad("events 배열이 필요합니다");
        }
        List<Map<String, Object>> events = new ArrayList<>();
        for (JsonNode e : evNode) {
            String key = text(e, "key");
            String file = text(e, "file");
            if (key == null || !KEY_RE.matcher(key).matches()) {
                throw bad("잘못된 key: " + key);
            }
            if (file == null || file.contains("..") || !FILE_RE.matcher(file).matches()) {
                throw bad("잘못된 file: " + file);
            }
            Path resolved = mediaDir.resolve("sfx").resolve(file).normalize();
            if (!resolved.startsWith(mediaDir) || !Files.isRegularFile(resolved)) {
                throw bad("음원이 없습니다: " + file);
            }
            double volume = e.path("volume").asDouble(0.5);
            double offset = e.path("offset").asDouble(0.0);
            if (volume < 0 || volume > 1.5) throw bad("volume 범위(0~1.5) 초과: " + key);
            if (offset < -5 || offset > 10) throw bad("offset 범위(-5~10) 초과: " + key);

            Map<String, Object> m = new LinkedHashMap<>();
            m.put("key", key);
            m.put("file", file);
            m.put("volume", volume);
            m.put("offset", offset);
            events.add(m);
        }
        int maxPerVideo = body.path("maxPerVideo").asInt(readBlock().maxPerVideo);
        if (maxPerVideo < 1 || maxPerVideo > 200) throw bad("maxPerVideo 범위(1~200) 초과");

        writeBlock(events, maxPerVideo);
        return getMapping();
    }

    // ── settings.yaml 입출력 ────────────────────────────────────────────

    private record SfxBlock(List<Map<String, Object>> events, int maxPerVideo, String tail) {}

    /**
     * {@code sfx:} 블록을 직접 파싱한다. 형식이 고정(2·4·6칸 들여쓰기)이라
     * YAML 파서를 끌어오지 않고 읽는다 — 파서를 쓰면 저장 때 주석이 사라진다.
     */
    private SfxBlock readBlock() {
        List<String> lines = readLines();
        List<Map<String, Object>> events = new ArrayList<>();
        int maxPerVideo = 18;
        StringBuilder tail = new StringBuilder();

        boolean inSfx = false, inActive = false;
        Map<String, Object> cur = null;
        for (String raw : lines) {
            if (raw.startsWith("sfx:")) { inSfx = true; continue; }
            if (!inSfx) continue;
            if (!raw.isBlank() && !raw.startsWith(" ")) break;   // sfx 블록 끝

            if (raw.startsWith("  active:")) { inActive = true; continue; }
            if (raw.startsWith("  ") && !raw.startsWith("    ") && !raw.isBlank()) {
                inActive = false;
                String t = raw.trim();
                if (t.startsWith("max_per_video:")) {
                    maxPerVideo = parseInt(valueOf(t), 18);
                } else {
                    tail.append(raw).append('\n');   // min_gap_sec 등은 그대로 보존
                }
                continue;
            }
            if (!inActive) {
                if (!raw.isBlank()) tail.append(raw).append('\n');
                continue;
            }
            if (raw.startsWith("    ") && !raw.startsWith("      ") && raw.trim().endsWith(":")) {
                cur = new LinkedHashMap<>();
                cur.put("key", raw.trim().replace(":", ""));
                cur.put("file", "");
                cur.put("volume", 0.5);
                cur.put("offset", 0.0);
                events.add(cur);
                continue;
            }
            if (cur != null && raw.startsWith("      ")) {
                String t = raw.trim();
                if (t.startsWith("file:")) cur.put("file", valueOf(t));
                else if (t.startsWith("volume:")) cur.put("volume", parseDouble(valueOf(t), 0.5));
                else if (t.startsWith("offset:")) cur.put("offset", parseDouble(valueOf(t), 0.0));
            }
        }
        return new SfxBlock(events, maxPerVideo, tail.toString());
    }

    private void writeBlock(List<Map<String, Object>> events, int maxPerVideo) {
        String src = readAll();
        int start = src.indexOf("sfx:");
        if (start < 0 || (start > 0 && src.charAt(start - 1) != '\n')) {
            throw new ResponseStatusException(HttpStatus.INTERNAL_SERVER_ERROR,
                "settings.yaml 에서 sfx 블록을 찾지 못했습니다");
        }
        // sfx 블록의 끝 = 들여쓰기 없는 다음 줄
        int end = src.length();
        int i = src.indexOf('\n', start);
        while (i >= 0 && i + 1 < src.length()) {
            int nl = src.indexOf('\n', i + 1);
            String line = src.substring(i + 1, nl < 0 ? src.length() : nl);
            if (!line.isBlank() && !line.startsWith(" ")) { end = i + 1; break; }
            if (nl < 0) { end = src.length(); break; }
            i = nl;
        }

        SfxBlock old = readBlock();
        StringBuilder b = new StringBuilder("sfx:\n  active:\n");
        for (Map<String, Object> e : events) {
            b.append("    ").append(e.get("key")).append(":\n");
            b.append("      file: ").append(e.get("file")).append('\n');
            b.append("      volume: ").append(e.get("volume")).append('\n');
            b.append("      offset: ").append(e.get("offset")).append('\n');
        }
        b.append("  max_per_video: ").append(maxPerVideo).append('\n');
        b.append(old.tail);

        String out = src.substring(0, start) + b + src.substring(end);
        try {
            Files.writeString(settingsPath, out, StandardCharsets.UTF_8);
        } catch (IOException ex) {
            throw new ResponseStatusException(HttpStatus.INTERNAL_SERVER_ERROR,
                "settings.yaml 저장 실패: " + ex.getMessage());
        }
        log.info("[sfx] 매핑 갱신: {}개 이벤트, 상한 {}", events.size(), maxPerVideo);
    }

    // ── 라이브러리 목록 ─────────────────────────────────────────────────

    private List<Map<String, Object>> listLibrary() {
        List<Map<String, Object>> out = new ArrayList<>();
        Path sfxDir = mediaDir.resolve("sfx");

        List<Map<String, String>> cur = scan(sfxDir, "");
        if (!cur.isEmpty()) out.add(Map.of("category", "current", "files", cur));

        for (String parent : List.of("_candidates", "_library")) {
            Path root = sfxDir.resolve(parent);
            if (!Files.isDirectory(root)) continue;
            try (Stream<Path> dirs = Files.list(root)) {
                dirs.filter(Files::isDirectory)
                    .sorted(Comparator.comparing(p -> p.getFileName().toString()))
                    .forEach(d -> {
                        String rel = parent + "/" + d.getFileName();
                        List<Map<String, String>> fs = scan(d, rel + "/");
                        if (!fs.isEmpty()) {
                            out.add(Map.of("category", d.getFileName().toString(), "files", fs));
                        }
                    });
            } catch (IOException ex) {
                log.warn("[sfx] 라이브러리 목록 실패: {}", root, ex);
            }
        }
        return out;
    }

    private List<Map<String, String>> scan(Path dir, String prefix) {
        List<Map<String, String>> out = new ArrayList<>();
        if (!Files.isDirectory(dir)) return out;
        try (Stream<Path> fs = Files.list(dir)) {
            fs.filter(Files::isRegularFile)
              .filter(p -> p.getFileName().toString().toLowerCase().endsWith(".wav"))
              .sorted(Comparator.comparing(p -> p.getFileName().toString()))
              .forEach(p -> out.add(Map.of(
                  "name", p.getFileName().toString(),
                  "path", prefix + p.getFileName())));
        } catch (IOException ex) {
            log.warn("[sfx] 목록 실패: {}", dir, ex);
        }
        return out;
    }

    // ── 유틸 ────────────────────────────────────────────────────────────

    private List<String> readLines() {
        return List.of(readAll().split("\n", -1));
    }

    private String readAll() {
        try {
            return Files.readString(settingsPath, StandardCharsets.UTF_8);
        } catch (IOException ex) {
            throw new ResponseStatusException(HttpStatus.INTERNAL_SERVER_ERROR,
                "settings.yaml 을 읽지 못했습니다 (" + settingsPath + "): " + ex.getMessage());
        }
    }

    private static String valueOf(String trimmed) {
        int c = trimmed.indexOf(':');
        String v = c < 0 ? "" : trimmed.substring(c + 1);
        int h = v.indexOf('#');
        if (h >= 0) v = v.substring(0, h);
        return v.trim();
    }

    private static String text(JsonNode n, String field) {
        JsonNode v = n.get(field);
        return (v == null || v.isNull()) ? null : v.asText();
    }

    private static int parseInt(String s, int dflt) {
        try { return Integer.parseInt(s.trim()); } catch (Exception e) { return dflt; }
    }

    private static double parseDouble(String s, double dflt) {
        try { return Double.parseDouble(s.trim()); } catch (Exception e) { return dflt; }
    }

    /**
     * 잘못된 입력은 IllegalArgumentException 으로 던진다.
     * 전역 핸들러(GlobalExceptionHandler)가 이 타입만 400 으로 내려주고
     * ResponseStatusException 은 500 으로 뭉개기 때문이다.
     */
    private static IllegalArgumentException bad(String msg) {
        return new IllegalArgumentException(msg);
    }
}
