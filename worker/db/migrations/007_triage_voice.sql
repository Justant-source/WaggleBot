-- 007: 옥석판별 AI 적합도 + 게시글별 TTS 보이스/생성지시문 컬럼 추가
-- posts 테이블: AI 분석 결과 컬럼 추가 + last_error (Flyway V3와 동기화)
-- contents 테이블: 보이스 선택 및 생성 지시문 컬럼 추가
ALTER TABLE posts
    ADD COLUMN IF NOT EXISTS ai_score INT NULL,
    ADD COLUMN IF NOT EXISTS ai_reason VARCHAR(500) NULL,
    ADD COLUMN IF NOT EXISTS ai_recommended TINYINT(1) NULL,
    ADD COLUMN IF NOT EXISTS ai_analyzed_at DATETIME(6) NULL,
    ADD COLUMN IF NOT EXISTS last_error VARCHAR(1000) NULL;

ALTER TABLE posts
    ADD INDEX IF NOT EXISTS ix_posts_status_ai_score (status, ai_score);

ALTER TABLE contents
    ADD COLUMN IF NOT EXISTS tts_voice VARCHAR(32) NULL,
    ADD COLUMN IF NOT EXISTS gen_instructions VARCHAR(1000) NULL;
