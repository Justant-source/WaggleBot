CREATE TABLE IF NOT EXISTS jobs (
  id          BIGINT PRIMARY KEY AUTO_INCREMENT,
  job_type    VARCHAR(40)  NOT NULL,
  post_id     BIGINT       NULL,
  status      VARCHAR(20)  NOT NULL DEFAULT 'PENDING',
  payload     JSON         NULL,
  result      JSON         NULL,
  error       TEXT         NULL,
  created_at  DATETIME(6)  NOT NULL,
  updated_at  DATETIME(6)  NOT NULL,
  INDEX ix_jobs_status_type (status, job_type),
  INDEX ix_jobs_post (post_id)
);
