-- 006: posts 테이블에 last_error 컬럼 추가
-- 파이프라인 실패 원인을 UI에 표시하기 위한 컬럼
ALTER TABLE posts ADD COLUMN IF NOT EXISTS last_error VARCHAR(1000) NULL;
