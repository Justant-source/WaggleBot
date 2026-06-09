package com.wagglebot.common;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/**
 * Python ScriptData.from_json/to_json 의 Java 미러.
 * Content.summary_text(TEXT) ↔ ScriptDataDto 변환.
 *
 * CRITICAL: 이 클래스는 Python round-trip 호환을 보장해야 한다.
 * 변경 시 반드시 Python ScriptData.from_json(java_output)으로 검증할 것.
 */
@Component
@Slf4j
public class ScriptDataMapper {

    private static final ObjectMapper MAPPER = new ObjectMapper();
    private static final TypeReference<Map<String, Object>> MAP_REF = new TypeReference<>() {};

    /** summary_text(JSON 또는 레거시 평문) → ScriptDataDto */
    public ScriptDataDto fromJson(String summaryText) {
        if (summaryText == null || summaryText.isBlank()) return emptyScript();
        try {
            Map<String, Object> d = MAPPER.readValue(summaryText, MAP_REF);
            List<Object> bodyRaw = (List<Object>) d.getOrDefault("body", List.of());
            List<Map<String, Object>> body = new ArrayList<>();
            for (Object item : bodyRaw) {
                if (item instanceof String s) {
                    // 하위 호환: 기존 str → dict 변환 (Python from_json과 동일)
                    body.add(Map.of("line_count", 1, "lines", List.of(s)));
                } else if (item instanceof Map<?,?> m) {
                    body.add((Map<String, Object>) m);
                }
            }
            return ScriptDataDto.builder()
                .hook((String) d.getOrDefault("hook", ""))
                .body(body)
                .closer((String) d.getOrDefault("closer", ""))
                .titleSuggestion((String) d.getOrDefault("title_suggestion", ""))
                .tags((List<String>) d.getOrDefault("tags", List.of()))
                .mood((String) d.getOrDefault("mood", "daily"))
                .build();
        } catch (Exception e) {
            log.debug("ScriptData JSON 파싱 실패, 레거시 평문으로 처리: {}", e.getMessage());
            // 레거시 평문 — Python Content.get_script() 처리와 동일
            return ScriptDataDto.builder()
                .hook(summaryText.substring(0, Math.min(summaryText.length(), 15)))
                .body(List.of(Map.of("line_count", 1, "lines", List.of(summaryText))))
                .closer("")
                .titleSuggestion("")
                .tags(List.of())
                .mood("daily")
                .build();
        }
    }

    /** ScriptDataDto → summary_text JSON 문자열 (Python to_json 호환) */
    public String toJson(ScriptDataDto dto) {
        try {
            Map<String, Object> map = new java.util.LinkedHashMap<>();
            map.put("hook", dto.getHook());
            map.put("body", dto.getBody());
            map.put("closer", dto.getCloser());
            map.put("title_suggestion", dto.getTitleSuggestion());
            map.put("tags", dto.getTags());
            map.put("mood", dto.getMood());
            return MAPPER.writeValueAsString(map);
        } catch (Exception e) {
            throw new RuntimeException("ScriptData JSON 직렬화 실패", e);
        }
    }

    private ScriptDataDto emptyScript() {
        return ScriptDataDto.builder()
            .hook("").body(List.of()).closer("").titleSuggestion("").tags(List.of()).mood("daily")
            .build();
    }
}
