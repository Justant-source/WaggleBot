package com.wagglebot.domain;

import com.fasterxml.jackson.databind.JsonNode;
import com.wagglebot.common.converter.JsonNodeConverter;
import jakarta.persistence.*;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

import java.time.LocalDateTime;

@Entity
@Table(name = "contents")
@Getter @Setter @NoArgsConstructor
public class Content {
    @Id @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "post_id", nullable = false, unique = true)
    private Long postId;

    /** ScriptData JSON 또는 레거시 평문. ScriptDataMapper로 파싱. */
    @Column(name = "summary_text", columnDefinition = "TEXT")
    private String summaryText;

    @Column(name = "audio_path", length = 255)
    private String audioPath;

    @Column(name = "video_path", length = 255)
    private String videoPath;

    @Convert(converter = JsonNodeConverter.class)
    @Column(name = "upload_meta", columnDefinition = "JSON")
    private JsonNode uploadMeta;

    @Convert(converter = JsonNodeConverter.class)
    @Column(name = "pipeline_state", columnDefinition = "JSON")
    private JsonNode pipelineState;

    @Column(name = "variant_group", length = 64)
    private String variantGroup;

    @Column(name = "variant_label", length = 32)
    private String variantLabel;

    @Convert(converter = JsonNodeConverter.class)
    @Column(name = "variant_config", columnDefinition = "JSON")
    private JsonNode variantConfig;

    @Column(name = "created_at", nullable = false)
    private LocalDateTime createdAt;
}
