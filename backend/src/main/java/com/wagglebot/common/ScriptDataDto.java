package com.wagglebot.common;

import lombok.Builder;
import lombok.Getter;
import java.util.List;
import java.util.Map;

/** Python ScriptData dataclass의 Java 미러. */
@Getter @Builder
public class ScriptDataDto {
    private String hook;
    private List<Map<String, Object>> body;
    private String closer;
    private String titleSuggestion;
    private List<String> tags;
    private String mood;
}
