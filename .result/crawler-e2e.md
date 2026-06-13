# 크롤러 E2E 테스트 및 버그 수정

## 1. 작업 결과

**6/7 크롤러 PASS** (fmkorea는 사이트 봇 차단 - 코드 문제 아님)

| 크롤러 | 결과 | listing | content | comments |
|--------|------|---------|---------|----------|
| nate_pann | ✅ PASS | 50건 | 978자 | 5개 |
| bobaedream | ✅ PASS | 20건 | 73자 | 20개 |
| dcinside | ✅ PASS | 96건 | 250자 | 17개 |
| instiz | ✅ PASS (수정) | 44건 | 287자 | 0 |
| theqoo | ✅ PASS (수정) | 25건 | 100자 | 0 |
| mlbpark | ✅ PASS (수정) | 63건 | 2자* | 306개 |
| fmkorea | 🚫 BLOCKED | 0건 | - | - |

*mlbpark listing 1번 포스트가 "마지막글 - ㅋㅋ" 이어서 2자. listing 3번 이후 포스트는 정상.

---

## 2. 수정 내용

### 공통 근본 원인 (instiz/theqoo/mlbpark listing 0건)
- **`config/crawler.py`** — `Accept-Encoding: gzip, deflate, br` → `gzip, deflate`
  - 컨테이너에 brotli 패키지 미설치 상태에서 `br` 광고 → Brotli 압축 응답 디코딩 실패 → BeautifulSoup에 이진 데이터 전달 → 셀렉터 0건

### instiz (`worker/crawlers/instiz.py`)
- `#memo_content_1` 셀렉터로 본문 추출 (기존 `.memo_content` → 스크립트 텍스트 '1' 반환)
- 이미지 전용 포스트: `content < 10자 + images 존재` → `[이미지 N장]` 폴백
- 댓글: `#ajax_comment tr.cmt_view` + `span[id^='n']` 구조로 변경
- 조회수: `span#hit` 직접 선택
- 이미지 URL `//cdn...` → `https:` 자동 보정

### theqoo (`worker/crawlers/theqoo.py`)
- 더쿠가 XE → Rhymix 마이그레이션 후 HTML 구조 변경 → 셀렉터 전면 수정
  - 제목: `.theqoo_document_header .title`
  - 본문: `.document_viewer .xe_content`
  - 통계: `.count_container` 파싱
  - 댓글: `dispTheqooContentCommentListTheqoo` AJAX API

### mlbpark (`worker/crawlers/mlbpark.py`)
- 테이블 클래스: `bd_list` → `tbl_type01`
- 제목 셀: `td.title` → `td.t_left`
- 본문: `.view_textbody` → `div.view_context`
- 댓글: `div.reply_list > div.other_con|my_con > div.txt` 구조

### dcinside (`worker/crawlers/dcinside.py`)
- 출처 라인 regex 수정: `.*?`(non-greedy) → `.*`(greedy) → `[원본 보기]` 잔존 제거
- 단독 `[원본 보기]` 라인 별도 regex 추가
- 이미지 위주 포스트: `img[data-fileno]` 카운트, content < 20자면 `[이미지 N장]` 생성

### docker-compose + .env
- `env/docker-compose.yml` crawler 서비스에 `ENABLED_CRAWLERS` 환경변수 주입 추가
- `env/.env.example`에 `ENABLED_CRAWLERS` 항목 추가

---

## 3. 테스트 결과물 위치
- `worker/test/test_crawlers_e2e.py` — E2E 테스트 스크립트 (신규)

---

## 4. 수동 테스트 방법

```bash
# ai_worker 컨테이너에서 실행 (config 바인드 마운트가 정상 작동)
docker exec env-ai_worker-1 python3 -c "
import sys; sys.path.insert(0,'/app')
import crawlers
from crawlers.plugin_manager import CrawlerRegistry
for site in ['nate_pann','bobaedream','dcinside','instiz','theqoo','mlbpark']:
    c = CrawlerRegistry.get_crawler(site)
    listings = c.fetch_listing()
    print(site, len(listings), '건')
"
```

**crawler 컨테이너 적용을 위한 이미지 재빌드 필요:**
```bash
# Accept-Encoding 수정이 baked-in config에 반영되려면 rebuild 필요
docker compose -f env/docker-compose.yml build crawler
docker compose -f env/docker-compose.yml up -d crawler
```

**instiz/theqoo/mlbpark 활성화 (.env 수정):**
```
ENABLED_CRAWLERS=nate_pann,bobaedream,dcinside,fmkorea,instiz,theqoo,mlbpark
```
(fmkorea은 현재 봇 차단 상태라 수집 실패할 수 있음)

---

## 5. 추천 commit message
```
fix: 크롤러 4종 파서 수정 + Accept-Encoding br 제거

- config/crawler.py: Accept-Encoding에서 br(Brotli) 제거
  → 컨테이너 brotli 미설치 시 응답 디코딩 실패로 listing 0건 반환 방지
- instiz: #memo_content_1 셀렉터 수정, 댓글/조회수 파싱 개선
- theqoo: Rhymix 마이그레이션 후 전체 셀렉터 수정, AJAX 댓글 API 적용
- mlbpark: tbl_type01/t_left/view_context 등 실제 클래스명으로 수정
- dcinside: 출처라인 regex 수정, 이미지 전용 포스트 content 보완
- docker-compose: crawler 서비스에 ENABLED_CRAWLERS 환경변수 전달 추가
```

---

## 6. 갱신한 문서 목록
없음 (코드 수정만)

---

## 참고: fmkorea 봇 차단 현황
fmkorea는 서버에서 `Retry-After: 300`을 포함한 HTTP 430으로 차단. cloudscraper 라이브러리로
TLS 핑거프린트 우회 시도하나 현재 차단됨. 코드 버그 아님 — 사이트 측 Cloudflare 강화로 인한 이슈.
해결책: 주기적 IP 로테이션, Playwright 브라우저 자동화, 또는 해당 크롤러 일시 비활성화.
