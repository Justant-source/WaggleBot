# doc-sync

## 1. 작업 결과

전체 docs/ last-verified 갱신, migration 007 누락 컬럼 보완, 버그픽스 이력 현행화.
plugin_manager.py에 누락 함수 3개 추가로 테스트 7개 복구.

## 2. 수정 내용

### docs/ 갱신

- **모든 docs/*.md** `last-verified` 커밋 해시 `913e606` → `3ba0d15`
- **`docs/database.md`**
  - ER 다이어그램 posts에 `ai_score / ai_reason / ai_recommended / ai_analyzed_at` 추가 (migration 007)
  - ER 다이어그램 contents에 `tts_voice / gen_instructions` 추가 (migration 007)
  - posts 상세 표에 4개 AI 옥석판별 컬럼 + 인덱스 설명 추가
  - contents 상세 표에 `tts_voice`, `gen_instructions` 항목 추가
- **`docs/implementation-status.md`**
  - 마이그레이션 수 `006` → `007`
  - 버그픽스 5차~8차(미커밋) → 실제 커밋 해시로 교체
  - 9차~11차(현 세션 수정) 신규 행 추가

### 코드 수정

**`worker/crawlers/plugin_manager.py`** — 테스트에서 참조하나 미구현된 함수 3개 추가:
- `CrawlerRegistry.unregister(site_code)` — 특정 크롤러 등록 해제
- `CrawlerRegistry.clear()` — 레지스트리 전체 초기화 (테스트용)
- `auto_discover(package)` — 패키지 스캔 후 크롤러 모듈 reload·등록
  - `base.py` / `plugin_manager.py` reload 제외 (reload 시 BaseCrawler 클래스 객체 교체 → issubclass 실패)

## 3. 테스트 결과

```
test/test_plugin_system.py       7 passed  (기존 ImportError → 전부 통과)
test/test_scene_policy.py        6 passed
test/test_scene_idx_mapping.py   8 passed
test/test_prompt_engine.py       6 passed
test/test_monitoring.py          3 passed
test/test_e2e_structure_improve.py 21 passed (unit)
총 51 passed, 0 failed
```

## 4. 수동 테스트 방법

```bash
docker compose exec ai_worker python -m pytest test/test_plugin_system.py -v
```

## 5. 추천 commit message

```
fix: plugin_manager auto_discover/clear/unregister 추가 + docs 동기화
```

## 6. DOC-MAP 기준 갱신한 문서 목록

- `docs/database.md` — migration 007 컬럼 추가
- `docs/implementation-status.md` — 버그 픽스 이력 현행화, 마이그레이션 수
- `docs/api.md`, `docs/architecture.md`, `docs/config.md`, `docs/pipeline.md`, `docs/services.md`, `docs/improvements.md` — last-verified 갱신
