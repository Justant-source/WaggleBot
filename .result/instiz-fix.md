# instiz-fix

## 1. 작업 결과

인스티즈 크롤러 `fetch_listing()` 0건 반환 버그를 수정했다. 수정 후 listing 47~49건, 상세 제목/본문/통계/댓글 모두 정상 파싱 확인.

## 2. 수정 내용

### 근본 원인 — Brotli 압축 응답 미디코딩

파일: `config/crawler.py`

`REQUEST_HEADERS`의 `Accept-Encoding: gzip, deflate, br` 에서 `br`(Brotli)을 제거.

- 구: `"Accept-Encoding": "gzip, deflate, br"`
- 신: `"Accept-Encoding": "gzip, deflate"`

`brotli`/`brotlicffi` 패키지가 컨테이너에 설치되지 않은 상태에서 `br`을 광고하면 인스티즈가 Brotli 압축 응답을 반환하고, `requests`가 이를 디코딩하지 못해 BeautifulSoup에 깨진 바이트가 전달된다. 결과적으로 모든 CSS 셀렉터가 0건을 반환한다.  
(다른 크롤러 사이트들은 gzip으로 응답해 영향 없었음.)

---

### parse_post 셀렉터 교정

파일: `worker/crawlers/instiz.py`

#### 제목
- 구: `.memo_subject`, `h2.title` — 페이지에 존재하지 않음
- 신: `#nowsubject` + `.cmt/.cmt2/.cmt3` 자식 스팬 decompose()

제목 링크 `<a>` 안의 `<span id="nowsubject">` 내부에 `<span class="cmt3">182</span>` 형태로 댓글 수가 포함되어 있어 제거 후 추출해야 한다.

#### 조회수
- 구: `soup.get_text()` 전체에서 `조회\s*:?\s*([\d,]+)` 패턴 — 검색 폼의 "조회순" 텍스트에 오탐 위험
- 신: `span#hit` 직접 선택

#### 추천수
- 정적 HTML에 추천 수 미노출 (AJAX 로드) → `likes = 0` 고정

#### 본문
- 구: `.memo_content`, `.content_view`
- 신: `#memo_content_1`, `.memo_content` (기존 fallback 유지)

이미지 전용 게시글은 텍스트가 거의 없는 것이 정상이며 `images` 필드로 대체된다. 프로토콜 없는 `//cdn.instiz.net/...` URL에 `https:` 접두사 자동 보정 추가.

#### 댓글
- 구: `.comment_wrap .comment_list li`, `.cmt_list li` — 구조 없음
- 신: `#ajax_comment tr.cmt_view` 행 순회
  - 작성자: `td.comment_memo .href`
  - 본문: `td.comment_memo span[id^='n']`
  - 로그인 안내 문구("로그인 후 이용") 필터링
  - 공감수: 정적 HTML 미노출 → 0

#### 목록 제목 댓글 수 제거
- 목록 페이지 링크 내 `.cmt/.cmt2/.cmt3` 스팬에 댓글 수가 포함됨
- `link.select(".cmt, .cmt2, .cmt3")` 순회 후 `decompose()` 하여 숫자 없는 순수 제목 저장

## 3. 테스트 결과

```
listing count: 47
sample: {'origin_id': '7865468', 'title': '현재 𝙅𝙊𝙉𝙉𝘼 심각하다는 티빙 유출사태..JPG', 'url': '...'}
title: 한국인한테는 너무 쉽다는 여기 진짜 한국인이 하는 것 같아?에 대한 대답
content len: 61
stats: {'views': 33422, 'likes': 0, 'comments_count': 1}
comments: 1
```

## 4. 수동 테스트 방법

```bash
docker exec env-ai_worker-1 python3 -c "
import sys; sys.path.insert(0, '/app')
import crawlers
from crawlers.plugin_manager import CrawlerRegistry
c = CrawlerRegistry.get_crawler('instiz')
listings = c.fetch_listing()
print('listing count:', len(listings))
if listings:
    detail = c.parse_post(listings[0]['url'])
    print('title:', detail['title'][:60])
    print('stats:', detail['stats'])
    print('comments:', len(detail['comments']))
"
```

## 5. 추천 commit message

```
fix: 인스티즈 크롤러 — Brotli 압축 미지원 수정 + parse_post 셀렉터 교정
```

## 6. 갱신한 문서 목록

없음 (크롤러 내부 버그 픽스, 구조 변경 없음)
