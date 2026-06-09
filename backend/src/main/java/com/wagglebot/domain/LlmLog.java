package com.wagglebot.domain;

import com.fasterxml.jackson.databind.JsonNode;
import com.wagglebot.common.converter.JsonNodeConverter;
import jakarta.persistence.*;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

import java.time.LocalDateTime;

@Entity
@Table(name = "llm_logs")
@Getter @Setter @NoArgsConstructor
public class LlmLog {
    @Id @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "post_id")
    private Long postId;

    @Column(name = "call_type", nullable = false, length = 32)
    private String callType;

    @Column(name = "model_name", length = 64)
    private String modelName;

    @Column(length = 32)
    private String strategy;

    @Column(name = "image_count", nullable = false)
    private Integer imageCount = 0;

    @Column(name = "content_length", nullable = false)
    private Integer contentLength = 0;

    @Column(name = "prompt_text", columnDefinition = "TEXT")
    private String promptText;

    @Column(name = "raw_response", columnDefinition = "TEXT")
    private String rawResponse;

    @Convert(converter = JsonNodeConverter.class)
    @Column(name = "parsed_result", columnDefinition = "JSON")
    private JsonNode parsedResult;

    @Column(nullable = false)
    private Boolean success = true;

    @Column(name = "error_message", columnDefinition = "TEXT")
    private String errorMessage;

    @Column(name = "duration_ms")
    private Integer durationMs;

    @Column(name = "created_at", nullable = false)
    private LocalDateTime createdAt;
}
