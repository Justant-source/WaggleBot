# 크롤러 사이트 추가 + Telegram 트레이 알림

## 1. 작업 결과

- 신규 크롤러 3종 구현: 인스티즈, 더쿠, MLB파크
- `BaseCrawler`에 고점수/자동승인 게시글 즉시 Telegram 알림 기능 추가

## 2. 수정 내용

### 신규 파일

**`worker/crawlers/instiz.py`** — 인스티즈 실시간 베스트
- URL: `https://www.instiz.net/pt`
- `a[href*='/pt/']` 링크에서 게시글 ID 파싱
- 내용: `.memo_content` / `.content_view`, 댓글: `.comment_list li`

**`worker/crawlers/theqoo.py`** — 더쿠 HOT 게시판
- URL: `https://theqoo.net/hot`
- XE(XpressEngine) 기반 — `document_srl=숫자` 패턴으로 게시글 식별
- 내용: `.xe_content`, 댓글: `#comment_list .comment`

**`worker/crawlers/mlbpark.py`** — MLB파크 불펜+자유게시판
- URL: `https://mlbpark.donga.com/mlbpark/b.php?b=bullpen`, `?b=bullpen2`
- `table.bd_list td.title a`에서 `id=숫자` 파라미터 파싱
- 내용: `.view_textbody`, 댓글: `.comment_list li`

### 기존 파일 수정

**`worker/crawlers/base.py`**
- `_notify_tray(title, url, score, auto_approved)` 메서드 추가
- `_upsert(session, origin_id, detail, url="")` — `url` 파라미터 추가
- `run()`에서 `_upsert(..., url=item["url"])` 전달
- 신규 게시글 저장 후 `auto_approved` or `score >= TELEGRAM_CRAWL_ALERT_THRESHOLD`이면 hook POST

**`config/settings.py`**
```python
TELEGRAM_HOOK_URL: str = os.getenv("TELEGRAM_HOOK_URL", "http://telegram-bridge:3847/hook")
TELEGRAM_CRAWL_ALERT_ENABLED: bool = os.getenv("TELEGRAM_CRAWL_ALERT", "false").lower() == "true"
TELEGRAM_CRAWL_ALERT_THRESHOLD: float = float(os.getenv("TELEGRAM_ALERT_THRESHOLD", "100"))
```

**`worker/crawlers/__init__.py`** — 신규 크롤러 3종 import 추가 (데코레이터 실행 보장)
```python
import crawlers.instiz   # noqa: F401
import crawlers.theqoo   # noqa: F401
import crawlers.mlbpark  # noqa: F401
```

**`env/docker-compose.yml`** — crawler 서비스 환경변수 추가
```yaml
TELEGRAM_HOOK_URL: ${TELEGRAM_HOOK_URL:-http://telegram-bridge:3847/hook}
TELEGRAM_CRAWL_ALERT: ${TELEGRAM_CRAWL_ALERT:-false}
TELEGRAM_ALERT_THRESHOLD: ${TELEGRAM_ALERT_THRESHOLD:-100}
```

**`docs/services.md`**, **`docs/implementation-status.md`** — 변경사항 반영

## 3. 테스트 결과물 위치

없음 (컨테이너 실행 없이 정적 분석만)

## 4. 수동 테스트 방법

```bash
# 크롤러 등록 확인
docker compose -f env/docker-compose.yml exec crawler python main.py --list
# → instiz, theqoo, mlbpark 출력 확인

# 크롤러 1회 실행 (ENABLED_CRAWLERS에 추가 필요)
# env/.env:
ENABLED_CRAWLERS=nate_pann,instiz,theqoo,mlbpark
docker compose -f env/docker-compose.yml exec crawler python main.py --once

# Telegram 알림 테스트 (트레이 알림 활성화)
# env/.env:
TELEGRAM_CRAWL_ALERT=true
TELEGRAM_ALERT_THRESHOLD=50   # 낮은 임계값으로 테스트
```

> **주의**: 새 크롤러의 CSS 셀렉터는 실제 사이트 HTML 구조에 맞춰 검증 후 보정이 필요할 수 있음.
> 수집 실패 시 `docker compose logs crawler` → `Failed to parse`/`skip` 로그로 어느 셀렉터가 빗나갔는지 확인.

## 5. 추천 commit message

```
feat: 크롤러 3종 추가(인스티즈·더쿠·MLB파크) + Telegram 트레이 알림
```

## 6. DOC-MAP 기준 갱신한 문서 목록

- `docs/services.md` — crawler 서비스 플러그인 목록, Telegram 알림 env 추가 (`docker-compose.yml` 변경 규칙)
- `docs/implementation-status.md` — 크롤러 현황, 신규 섹션 (버그픽스 배치 → implementation-status 갱신 규칙)
