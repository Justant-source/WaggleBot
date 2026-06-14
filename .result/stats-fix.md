# stats-fix

## 1. 작업 결과

수신함(`/admin/inbox`)에서 모든 커뮤니티의 추천/댓글수 표시 현황을 전수조사하고
인스티즈의 댓글수 77% 누락 버그를 수정했다.

| 사이트 | 이슈 | 결과 |
|---|---|---|
| dcinside | 정상 | ✅ 유지 |
| nate_pann | 정상 (10% 실제 추천0) | ✅ 유지 |
| bobaedream | 정상 | ✅ 유지 |
| fmkorea | 정상 | ✅ 유지 |
| **instiz** | 댓글수 77% 0 (BUG) | ✅ **수정** |
| theqoo | 추천 0 = 사이트 기능 없음 | ✅ 정상 |
| mlbpark | 추천 73% 0 = 실제 값 확인됨 | ✅ 정상 |

## 2. 수정 내용

**파일: `worker/crawlers/instiz.py`**

### 근본 원인

인스티즈 댓글은 `#ajax_comment` 영역에 JavaScript로 동적 로딩된다.
기존 코드 `comments_count: len(comments)`는 정적 HTML에서 파싱된 댓글 수이므로
항상 0~소수만 반환했다.

### 해결책

`#nowsubject .cmt` span에 총 댓글수가 정적으로 렌더링됨을 확인:
```html
<span id="nowsubject">제목텍스트<span class="cmt" title="유효 댓글 수 132">173</span></span>
```

단, 기존 코드가 title 추출 전에 `.cmt` span들을 `decompose()`로 제거하므로,
**decompose 이전에 값을 먼저 읽도록** 순서 변경:

```python
# decompose 전에 .cmt 텍스트 선독
cmt_span = title_el.select_one(".cmt") if title_el else None
_page_comments_count = self._parse_int(self._text(cmt_span)) if cmt_span else 0
# 이후 decompose로 제목 정제...

# 통계 반환 시
comments_count = _page_comments_count or len(comments)
```

### 기존 DB 데이터 소급 적용

수정 전 저장된 502개 `comments_count=0` 게시글을 일괄 재파싱하여
97개 업데이트 (나머지 405개: 삭제된 게시글 또는 실제 댓글 0).

## 3. 테스트 결과

수정 전: `stats: {'views': 110482, 'likes': 0, 'comments_count': 1}`
수정 후: `stats: {'views': 110884, 'likes': 0, 'comments_count': 173}`

DB 통계 변화:
- instiz 댓글수 > 0 비율: 153/660 → 255/660 (+102개, 나머지는 삭제글/실제 0)

## 4. 수동 테스트 방법

```bash
docker compose -f env/docker-compose.yml exec ai_worker python3 -c "
import sys; sys.path.insert(0, '/app')
from crawlers.instiz import InstizCrawler
c = InstizCrawler()
r = c.parse_post('https://www.instiz.net/pt/7866491')
print('stats:', r['stats'])
"
```

예상 결과: `comments_count` > 0 (실제 댓글 수)

## 5. 추천 commit message

```
fix: 인스티즈 댓글수 0 버그 수정 — #nowsubject .cmt decompose 순서 교정
```

## 6. 갱신한 문서 목록

없음 (크롤러 내부 버그 픽스)
