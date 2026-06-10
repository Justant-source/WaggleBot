# feedback-loop

## 1. 작업 결과

성과 피드백 루프 및 자동 승인의 4가지 버그/누락을 수정·구현 완료.

| 항목 | 유형 | 파일 |
|------|------|------|
| `feedback.py` 레거시 import 교체 | 버그 수정 | `worker/analytics/feedback.py` |
| `handlers.py` `call_ollama_raw` 교체 | 버그 수정 | `worker/dashboard_worker/handlers.py:119` |
| `handlers.py` `generate_structured_insights` 잘못된 호출 | 버그 수정 | `worker/dashboard_worker/handlers.py:230,239` |
| `collector.py` 신규 구현 | 누락 파일 | `worker/analytics/collector.py` |
| 자동 승인 (auto_approve) 로직 | 신규 구현 | `worker/crawlers/base.py:304` |

## 2. 수정 내용

### feedback.py
- `from ai_worker.script.client import call_ollama_raw` → `from ai_worker.llm.transport import call_llm_raw`
- `call_ollama_raw(...)` → `call_llm_raw(...)` (CLAUDE.md 규칙: transport 경유 필수)

### handlers.py
- `_handle_ai_fitness`: `call_ollama_raw` → `call_llm_raw` (transport에서 직접 import)
- `_handle_ai_insight`: `generate_structured_insights(model=model)` 잘못된 호출 수정
  - `collect_analytics()` → `build_performance_summary(db)` → `generate_structured_insights(data, llm_model=...)` 순서로 재구성
  - 누락된 `performance_data` 인자 추가, `model=` → `llm_model=` 키워드 수정
- `_handle_feedback_apply`: 동일 수정

### collector.py (신규)
- `collect_analytics(max_posts=50)` 구현
- UPLOADED 상태 포스트를 최대 50개 조회
- `YouTubeUploader.fetch_analytics(video_id)` 호출
- `content.upload_meta["youtube"]["analytics"]` 에 통계 저장 후 commit
- 반환: 업데이트된 포스트 수

### base.py — 자동 승인
- `session.flush()` 직후, 신규 게시글에만 적용
- `load_pipeline_config()` 로드 → `auto_approve_enabled=true` && `score >= auto_approve_threshold`이면 `PostStatus.APPROVED`로 직행
- try/except로 감싸 설정 로드 실패 시 COLLECTED 유지 (안전 폴백)

## 3. 테스트 결과물 저장 위치

정적 분석 통과 (call_ollama_raw 잔존 0곳 확인):
```
OK worker/analytics/feedback.py
OK worker/analytics/collector.py
OK worker/dashboard_worker/handlers.py
```

## 4. 수동 테스트 방법

### 자동 승인 테스트
```bash
# pipeline.json에서 auto_approve_enabled=true, auto_approve_threshold=50 으로 낮춤
# 크롤러 실행 → 새 게시글 수집 → DB 확인
docker compose -f env/docker-compose.yml exec crawler python -c "
from crawlers.plugin_manager import CrawlerRegistry
from db.session import SessionLocal
with SessionLocal() as s:
    from db.models import Post, PostStatus
    count = s.query(Post).filter_by(status=PostStatus.APPROVED).count()
    print('APPROVED posts:', count)
"
```

### 피드백 루프 테스트
```bash
# AI_INSIGHT job enqueue (대시보드 → 분석 → LLM 인사이트 버튼)
# dashboard_worker 로그 확인
docker compose -f env/docker-compose.yml logs --tail 50 dashboard_worker
# config/feedback_config.json 확인
cat config/feedback_config.json
```

## 5. 추천 commit message

```
fix: 피드백 루프 버그 수정 + collector.py 구현 + 자동 승인 추가

- feedback.py: call_ollama_raw → call_llm_raw (transport 직접 import)
- handlers.py: generate_structured_insights 잘못된 시그니처 수정 (performance_data 누락, model→llm_model)
- handlers.py: _handle_ai_fitness call_ollama_raw → call_llm_raw
- analytics/collector.py: 신규 구현 (UPLOADED 포스트 YouTube 통계 수집)
- crawlers/base.py: auto_approve_enabled/threshold 기반 자동 승인 로직 추가
```
