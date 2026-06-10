# db-config

## 1. 작업 결과

DB 마이그레이션 2개(Flyway V3 + Worker 007)와 Config JSON 2개(voices.json, prompt_presets.json) 신규 생성.
docker-compose.yml에 volumes 2곳 추가 완료.

| 항목 | 파일 | 내용 |
|------|------|------|
| Flyway 마이그레이션 | `backend/.../V3__triage_voice.sql` | posts 5컬럼 + 인덱스 + contents 2컬럼 |
| Worker 마이그레이션 | `worker/db/migrations/007_triage_voice.sql` | 동일 DDL, runner.py 숫자 순서 실행 |
| 보이스 설정 | `config/voices.json` | 8개 보이스 key/label/file 매핑 |
| 프롬프트 프리셋 | `config/prompt_presets.json` | 6종 extra_instructions 원문 그대로 |
| Docker 볼륨 | `env/docker-compose.yml` | backend + dashboard_worker 2곳 추가 |

## 2. 수정 상세

### V3__triage_voice.sql / 007_triage_voice.sql
- `posts.ai_score INT NULL` — AI 적합도 점수 (0~100)
- `posts.ai_reason VARCHAR(500) NULL` — 판단 근거 요약
- `posts.ai_recommended TINYINT(1) NULL` — 추천 여부 (0/1)
- `posts.ai_analyzed_at DATETIME(6) NULL` — 분석 시각
- `posts.last_error VARCHAR(1000) NULL` — worker 006에만 있고 Flyway V2에 누락된 컬럼을 IF NOT EXISTS로 치유
- `ix_posts_status_ai_score (status, ai_score)` — 옥석판별 필터링 쿼리 인덱스
- `contents.tts_voice VARCHAR(32) NULL` — 게시글별 TTS 보이스 선택
- `contents.gen_instructions VARCHAR(1000) NULL` — 게시글별 생성 지시문

### config/voices.json
- `settings.py:284 VOICE_PRESETS`의 8개 키/파일명을 그대로 사용
- 한국어 라벨 추가 (UI 드롭다운 표시용)

### config/prompt_presets.json
- `worker/analytics/ab_test.py:30 VARIANT_PRESETS`의 extra_instructions 한국어 문자열 전체 그대로 사용
- 라벨은 사용자 요청 한국어 명칭으로 (hook_question→의문형 후킹 등)

### env/docker-compose.yml
- **backend** 서비스: `../assets/voices:/app/media/voices:ro` 추가
  - MediaController가 `/api/media/**`로 `/app/media/` 하위를 서빙 → 보이스 샘플 파일 자동 노출
- **dashboard_worker** 서비스: `../assets:/app/assets` 추가
  - fish_client.py가 `/app/assets/voices/{file}`로 참조 오디오 경로 조합 → 비기본 보이스 TTS 가능

## 3. 테스트 결과물 저장 위치

N/A (SQL 파일은 컨테이너 재시작 시 자동 적용, JSON은 앱 로드 시 읽힘)

## 4. 수동 테스트 방법

```bash
# 1. Worker 마이그레이션 확인
docker compose exec ai_worker python -m db.migrations.runner
# → "007_triage_voice 완료" 로그 확인

# 2. Flyway 마이그레이션 확인
docker compose logs backend | grep -E "V3|triage_voice"
# → "Successfully applied migration V3" 확인

# 3. 컬럼 추가 확인
docker compose exec db mariadb -u wagglebot -pwagglebot wagglebot \
  -e "SHOW COLUMNS FROM posts LIKE 'ai_%'; SHOW COLUMNS FROM contents LIKE 'tts_%';"

# 4. 보이스 파일 서빙 확인 (backend 재시작 후)
curl http://localhost:8080/api/media/voices/korean_man_default.wav -I
# → HTTP 200 확인

# 5. dashboard_worker 비기본 보이스 TTS
# 설정에서 anna 등 비기본 보이스 선택 후 TTS 미리듣기 → 무음 폴백 없이 정상 생성 확인
```

## 5. 추천 commit message

```
feat: DB 마이그레이션 007/V3 (AI 적합도 + 보이스 컬럼) + voices/prompt_presets JSON + docker volumes
```
