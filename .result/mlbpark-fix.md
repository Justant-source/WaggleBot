# mlbpark-fix

## 1. 작업 결과

MLB파크 크롤러 `fetch_listing()` 0건 반환 버그 및 `parse_post()` 셀렉터 오류를 수정했다. 수정 후 listing 63건, 상세 제목/본문/통계/댓글 모두 정상 파싱 확인.

## 2. 수정 내용

파일: `worker/crawlers/mlbpark.py`

### fetch_listing — 링크 셀렉터 변경
- 구: `table.bd_list td.title a, table tr td.tit a`
- 신: `table.tbl_type01 td.t_left a`

실제 HTML의 테이블 클래스는 `tbl_type01`이며 제목 셀 클래스는 `t_left`였다. `bd_list`, `td.title`, `td.tit`는 해당 페이지에 존재하지 않는다.

### parse_post — 제목 셀렉터
- 구: `h2.view_tit, .article_tit h2, .view_title`
- 신: `div.titles`

### parse_post — 본문 셀렉터
- 구: `.view_textbody, .article_body, .bd_view_contents`
- 신: `div.view_context`

### parse_post — 통계 추출 범위 축소
- 구: `soup.get_text()` 전체에서 regex
- 신: `ul.view_head`에서만 regex (오탐 방지)

### _parse_comments — 댓글 셀렉터
- 구: `.comment_list li, .reply_wrap li, .cmtlist li` — 이 구조는 존재하지 않음
- 신: `div.reply_list > div.other_con|my_con > div.txt_box > div.txt` 에서 `span.name`(작성자), `span.re_txt`(본문) 추출

## 3. 테스트 결과

```
listing count: 63
sample: {'origin_id': '3915358', 'title': '마지막글[289]', 'url': '...'}
title: 마지막글
content len: 2        # 실제 본문이 'ㅋㅋ' 2자 (정상)
stats: {'views': 315547, 'likes': 4, 'comments_count': 306}
comments: 306

title: 여기 글쓰기되나요?
  content len: 40
  stats: {'views': 215964, 'likes': 0, 'comments_count': 41}
  comments: 41
```

## 4. 수동 테스트 방법

```bash
docker exec env-ai_worker-1 bash -c "cd /app && PYTHONPATH=/app python3 -c \"
import crawlers
from crawlers.plugin_manager import CrawlerRegistry
c = CrawlerRegistry.get_crawler('mlbpark')
listings = c.fetch_listing()
print('listing count:', len(listings))
detail = c.parse_post(listings[0]['url'])
print('title:', detail['title'])
print('stats:', detail['stats'])
print('comments:', len(detail['comments']))
\""
```

## 5. 추천 commit message

```
fix: MLB파크 크롤러 셀렉터 수정 — tbl_type01/t_left/view_context/reply_list 기준
```

## 6. 갱신한 문서 목록

없음 (크롤러 내부 버그 픽스, 구조 변경 없음)
