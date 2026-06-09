CREATE TABLE IF NOT EXISTS posts (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    site_code VARCHAR(32) NOT NULL,
    origin_id VARCHAR(64) NOT NULL,
    title VARCHAR(512) NOT NULL,
    content TEXT,
    images JSON,
    stats JSON,
    status VARCHAR(32) NOT NULL DEFAULT 'COLLECTED',
    engagement_score DOUBLE NOT NULL DEFAULT 0.0,
    retry_count INT NOT NULL DEFAULT 0,
    created_at DATETIME(6) NOT NULL,
    updated_at DATETIME(6) NOT NULL,
    UNIQUE KEY uq_site_origin (site_code, origin_id),
    INDEX ix_posts_status_score (status, engagement_score),
    INDEX ix_posts_status_created (status, created_at),
    INDEX ix_posts_status (status),
    INDEX ix_posts_site_status (site_code, status),
    INDEX ix_posts_updated_at (updated_at),
    INDEX ix_posts_engagement_score (engagement_score)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS comments (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    post_id BIGINT NOT NULL,
    author VARCHAR(128) NOT NULL,
    content TEXT NOT NULL,
    content_hash VARCHAR(64) NOT NULL,
    likes INT NOT NULL DEFAULT 0,
    INDEX ix_comments_post_likes (post_id, likes),
    UNIQUE KEY uq_post_comment (post_id, author, content_hash),
    CONSTRAINT fk_comments_post FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS contents (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    post_id BIGINT NOT NULL UNIQUE,
    summary_text TEXT,
    audio_path VARCHAR(255),
    video_path VARCHAR(255),
    upload_meta JSON,
    pipeline_state JSON,
    variant_group VARCHAR(64),
    variant_label VARCHAR(32),
    variant_config JSON,
    created_at DATETIME(6) NOT NULL,
    CONSTRAINT fk_contents_post FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS llm_logs (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    post_id BIGINT,
    call_type VARCHAR(32) NOT NULL,
    model_name VARCHAR(64),
    strategy VARCHAR(32),
    image_count INT NOT NULL DEFAULT 0,
    content_length INT NOT NULL DEFAULT 0,
    prompt_text TEXT,
    raw_response TEXT,
    parsed_result JSON,
    success BOOLEAN NOT NULL DEFAULT TRUE,
    error_message TEXT,
    duration_ms INT,
    created_at DATETIME(6) NOT NULL,
    INDEX ix_llm_logs_post_id (post_id),
    INDEX ix_llm_logs_call_type (call_type),
    INDEX ix_llm_logs_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS crawl_blocklist (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    site_code VARCHAR(32) NOT NULL,
    origin_id VARCHAR(64) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    UNIQUE KEY uq_blocklist_site_origin (site_code, origin_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
