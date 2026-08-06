package com.wagglebot.domain;

import jakarta.persistence.*;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

import java.time.LocalDateTime;

@Entity
@Table(name = "comments")
@Getter @Setter @NoArgsConstructor
public class Comment {
    @Id @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "post_id", nullable = false)
    private Long postId;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "post_id", insertable = false, updatable = false)
    private Post post;

    @Column(nullable = false, length = 128)
    private String author;

    @Column(nullable = false, columnDefinition = "TEXT")
    private String content;

    @Column(name = "content_hash", nullable = false, length = 64)
    private String contentHash;

    @Column(nullable = false)
    private Integer likes = 0;

    /** 댓글 작성 시각 — 외부 ingest(Again Spring 등)에서 전달. 크롤러 댓글은 NULL 유지. */
    @Column(name = "created_at")
    private LocalDateTime createdAt;

    /** "author" | "partner" | "neutral" — Again Spring Shorts 댓글 씬 진영색 스타일용. */
    @Column(length = 16)
    private String side;
}
