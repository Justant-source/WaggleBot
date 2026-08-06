-- 008: 댓글 작성 시각(created_at) · 진영(side) 컬럼 추가 (Flyway V4와 동기화)
-- Again Spring Shorts 댓글 씬 — 실제 닉네임/추천수/작성시각/진영을 렌더러까지 전달하기 위함.
ALTER TABLE comments
    ADD COLUMN IF NOT EXISTS created_at DATETIME(6) NULL,
    ADD COLUMN IF NOT EXISTS side VARCHAR(16) NULL;
