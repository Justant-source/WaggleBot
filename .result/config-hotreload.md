# config-hotreload

## 1. 작업 결과

`use_content_processor` 설정 변경이 ai_worker 재시작 없이 동적으로 반영되도록 수정.
`content_processor 모드` E2E 풀 파이프라인 실행 확인.

## 2. 수정 내용

**파일:** `worker/ai_worker/core/processor.py:796`

```python
# 기존 — worker 시작 시 1회만 로드된 self.cfg 사용 (재시작 필요)
use_cp = self.cfg.get("use_content_processor") == "true"

# 수정 후 — 매 호출마다 5s TTL 캐시 통해 fresh config 읽음
use_cp = load_pipeline_config().get("use_content_processor") == "true"
```

**`config/pipeline.json`:** `use_content_processor` → `"true"` (전환 완료)

## 3. E2E 테스트 결과

- post 213, 214 모두 `PREVIEW_RENDERED`, `last_error=NULL`
- content_processor 모드: `전략=text_heavy`, LLM 청킹(9.28초), TTS 31프레임(72.1s), FFmpeg 렌더링 완료
- `_recover_stuck_posts` — 재시작 시 PROCESSING 고착 포스트 자동 APPROVED 복구 확인
- progress API: `failed:[]`, `PROCESSING:0`

## 4. 수동 테스트 방법

게시글 1건 APPROVED → `docker compose logs --tail 50 ai_worker` 에서 아래 확인:
```
[Pipeline LLM+TTS] content_processor 모드: 전략=...
LLM 청킹 완료: hook=...
[Pipeline Render] ✓ 완료: post_id=N → PREVIEW_RENDERED
```

## 5. 추천 commit message

```
fix: use_content_processor 매 호출마다 fresh config 읽도록 수정
```

## 6. DOC-MAP 기준 갱신한 문서 목록

없음
