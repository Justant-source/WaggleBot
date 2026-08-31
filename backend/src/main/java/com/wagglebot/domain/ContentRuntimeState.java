package com.wagglebot.domain;

import com.fasterxml.jackson.databind.JsonNode;
import com.wagglebot.common.converter.JsonNodeConverter;
import jakarta.persistence.Column;
import jakarta.persistence.Convert;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.IdClass;
import jakarta.persistence.Table;
import lombok.Getter;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;

/** Mutable runtime namespace, deliberately separate from immutable Content fields. */
@Entity
@Table(name = "content_runtime_state")
@IdClass(ContentRuntimeStateId.class)
@Getter @NoArgsConstructor
public class ContentRuntimeState {
    @Id @Column(name = "content_id")
    private Long contentId;

    @Id @Column(name = "state_key", length = 64)
    private String stateKey;

    @Convert(converter = JsonNodeConverter.class)
    @Column(name = "state_value", columnDefinition = "JSON", nullable = false)
    private JsonNode stateValue;

    @Column(name = "updated_at", nullable = false)
    private LocalDateTime updatedAt;
}
