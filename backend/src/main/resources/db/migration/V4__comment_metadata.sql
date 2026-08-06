-- V4: 댓글 작성 시각(created_at) · 진영(side) 컬럼 추가
-- Again Spring Shorts 댓글 씬 — 실제 닉네임/추천수/작성시각/진영을 렌더러까지 전달하기 위함.
-- MariaDB 11 IF NOT EXISTS 멱등 보장

ALTER TABLE comments
    ADD COLUMN IF NOT EXISTS created_at DATETIME(6) NULL,
    ADD COLUMN IF NOT EXISTS side VARCHAR(16) NULL;
