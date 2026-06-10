package com.wagglebot.domain;

import com.fasterxml.jackson.annotation.JsonIgnore;
import com.fasterxml.jackson.databind.JsonNode;
import com.wagglebot.common.PostStatus;
import com.wagglebot.common.converter.JsonNodeConverter;
import jakarta.persistence.*;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

import java.time.LocalDateTime;
import java.util.List;

@Entity
@Table(name = "posts")
@Getter @Setter @NoArgsConstructor
public class Post {
    @Id @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "site_code", nullable = false, length = 32)
    private String siteCode;

    @Column(name = "origin_id", nullable = false, length = 64)
    private String originId;

    @Column(nullable = false, length = 512)
    private String title;

    @Column(columnDefinition = "TEXT")
    private String content;

    @Convert(converter = JsonNodeConverter.class)
    @Column(columnDefinition = "JSON")
    private JsonNode images;

    @Convert(converter = JsonNodeConverter.class)
    @Column(columnDefinition = "JSON")
    private JsonNode stats;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private PostStatus status = PostStatus.COLLECTED;

    @Column(name = "engagement_score", nullable = false)
    private Double engagementScore = 0.0;

    @Column(name = "retry_count", nullable = false)
    private Integer retryCount = 0;

    @Column(name = "last_error", length = 1000)
    private String lastError;

    @Column(name = "ai_score")
    private Integer aiScore;

    @Column(name = "ai_reason", length = 500)
    private String aiReason;

    @Column(name = "ai_recommended")
    private Boolean aiRecommended;

    @Column(name = "ai_analyzed_at")
    private LocalDateTime aiAnalyzedAt;

    @Column(name = "created_at", nullable = false)
    private LocalDateTime createdAt;

    @Column(name = "updated_at", nullable = false)
    private LocalDateTime updatedAt;

    @JsonIgnore
    @OneToMany(mappedBy = "post", fetch = FetchType.LAZY)
    private List<Comment> comments;
}
