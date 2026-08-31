-- 009: long-running workers must not compete on contents.pipeline_state JSON.
-- One independently upserted state row per content/state_key prevents a
-- progress heartbeat from invalidating a render checkpoint snapshot.
CREATE TABLE IF NOT EXISTS content_runtime_state (
    content_id BIGINT NOT NULL,
    state_key VARCHAR(64) NOT NULL,
    state_value JSON NOT NULL,
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
        ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (content_id, state_key),
    CONSTRAINT fk_content_runtime_state_content
        FOREIGN KEY (content_id) REFERENCES contents(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Preserve existing operational data during the rolling upgrade. Runtime code
-- reads this table first and falls back to the legacy JSON only while needed.
INSERT IGNORE INTO content_runtime_state (content_id, state_key, state_value)
SELECT id, 'progress', JSON_EXTRACT(pipeline_state, '$.progress')
FROM contents
WHERE JSON_EXTRACT(pipeline_state, '$.progress') IS NOT NULL;

INSERT IGNORE INTO content_runtime_state (content_id, state_key, state_value)
SELECT id, 'render_checkpoint', JSON_OBJECT(
    'phase', JSON_EXTRACT(pipeline_state, '$.phase'),
    'video_scenes_done', JSON_EXTRACT(pipeline_state, '$.video_scenes_done'),
    'video_clips', JSON_EXTRACT(pipeline_state, '$.video_clips'),
    'total_scenes', JSON_EXTRACT(pipeline_state, '$.total_scenes')
)
FROM contents
WHERE JSON_EXTRACT(pipeline_state, '$.phase') IS NOT NULL;

INSERT IGNORE INTO content_runtime_state (content_id, state_key, state_value)
SELECT id, 'sla', JSON_OBJECT(
    'degraded', JSON_EXTRACT(pipeline_state, '$.degraded'),
    'degrade_reasons', JSON_EXTRACT(pipeline_state, '$.degrade_reasons'),
    'deadline_breached_at', JSON_EXTRACT(pipeline_state, '$.deadline_breached_at')
)
FROM contents
WHERE JSON_EXTRACT(pipeline_state, '$.degraded') IS NOT NULL;
