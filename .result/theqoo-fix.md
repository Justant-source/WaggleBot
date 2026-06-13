# theqoo 크롤러 수정

## 1. 작업 결과

listing 0건 반환 문제 완전 해결. listing 25건, parse_post title/stats/comments 정상 동작.

## 2. 수정 내용

### 근본 원인 — Brotli 압축 디코딩 실패

`config/crawler.py`의 `REQUEST_HEADERS`에 `Accept-Encoding: gzip, deflate, br`이 설정되어 있었으나, 컨테이너에 `brotli`/`brotlicffi` 패키지가 설치되어 있지 않았다. Cloudflare가 `br`을 광고하는 클라이언트에게 Brotli 압축 응답을 반환했고, `requests`가 이를 디코딩하지 못해 깨진 이진 데이터가 `resp.text`에 담겼다. BeautifulSoup이 이를 파싱해도 링크를 전혀 찾지 못했다.

**수정**: `config/crawler.py` — `Accept-Encoding: gzip, deflate, br` → `gzip, deflate`

### parse_post 셀렉터 전면 수정 (`worker/crawlers/theqoo.py`)

더쿠가 기존 XE에서 Rhymix로 마이그레이션하여 HTML 구조가 변경됨:

| 항목 | 기존 (작동 안 함) | 수정 후 |
|------|-------------------|---------|
| title | `h1.np_18px_span`, `.document_title`, `#bd_main h1` | `.theqoo_document_header .title` |
| stats | `page_text` regex `조회\s*:?` / `추천\s*:?` | `.theqoo_document_header .count_container` 숫자 파싱 (1번째=조회수, 2번째=댓글수) |
| comments | `#comment_list .comment` (HTML 파싱) | `POST /index.php` AJAX API (`act=dispTheqooContentCommentListTheqoo`) |

### 기타 개선 사항

- listing에서 앵커 링크(`#123_comment`) 제외 로직 추가 (기존에는 숫자 isdigit() 체크로만 걸렀으나 앵커가 포함된 경우 누락 가능)
- `?page=N` 파라미터 URL 정규화
- 더쿠는 추천/좋아요 기능 없음 → `likes=0` 명시
- 댓글: 비회원 차단 메시지(`비회원은 작성한 지`) 필터링
- `_extract_doc_srl()` 헬퍼로 URL/loadReply에서 srl 추출

## 3. 테스트 결과물 위치

없음 (docker exec 직접 실행)

## 4. 수동 테스트 방법

```bash
docker exec env-ai_worker-1 bash -c "cd /app && PYTHONPATH=/app python - <<'PYEOF'
import sys
sys.path.insert(0, '/app')
import crawlers
from crawlers.plugin_manager import CrawlerRegistry
c = CrawlerRegistry.get_crawler('theqoo')
listings = c.fetch_listing()
print(f'listing count: {len(listings)}')
if listings:
    print('sample:', listings[0])
    detail = c.parse_post('https://theqoo.net/hot/4240955256')
    print('title:', detail.get('title','')[:60])
    print('content len:', len(detail.get('content') or ''))
    print('stats:', detail.get('stats'))
    print('comments:', len(detail.get('comments') or []))
PYEOF"
```

기대값: listing count >= 1, title 비어있지 않음, stats.views > 0, comments >= 1 (어제 게시글 기준)

## 5. 추천 commit message

```
fix: theqoo 크롤러 Brotli 압축·Rhymix HTML 구조 대응

- config/crawler.py: Accept-Encoding에서 br 제거 (brotli 패키지 미설치)
- theqoo.py: title/stats 셀렉터 Rhymix 구조로 수정
- theqoo.py: 댓글을 dispTheqooContentCommentListTheqoo AJAX API로 교체
```

## 6. DOC-MAP 기준 갱신한 문서 목록

없음 (크롤러 버그픽스 — 설계 변경 없음)
