import logging
import re
import time

import requests
from bs4 import BeautifulSoup

from crawlers.base import BaseCrawler
from crawlers.plugin_manager import CrawlerRegistry

log = logging.getLogger(__name__)

BASE_URL = "https://www.instiz.net"


@CrawlerRegistry.register(
    "instiz",
    description="인스티즈 실시간 베스트 크롤러",
    enabled=True,
)
class InstizCrawler(BaseCrawler):
    site_code = "instiz"
    SECTIONS = [
        {"name": "실시간 베스트", "url": f"{BASE_URL}/pt"},
    ]

    # ------------------------------------------------------------------
    # Listing
    # ------------------------------------------------------------------

    def fetch_listing(self) -> list[dict]:
        posts: list[dict] = []
        seen: set[str] = set()

        for section in self.SECTIONS:
            try:
                resp = self._get(section["url"])
            except requests.RequestException:
                log.exception("Failed to fetch listing: %s", section["url"])
                continue

            soup = BeautifulSoup(resp.text, "html.parser")

            # 인스티즈 인기글 목록: href에 절대 URL /pt/<id> 포함 링크
            # 제목 안에 댓글 수(.cmt3 span)가 포함되므로 제거 후 추출
            for link in soup.select("a[href*='/pt/']"):
                href = link.get("href", "")
                m = re.search(r"/pt/(\d+)", href)
                if not m:
                    continue

                origin_id = m.group(1)
                if origin_id in seen:
                    continue

                # 댓글 수 스팬(.cmt, .cmt2, .cmt3) 제거 후 제목 추출
                for cmt_el in link.select(".cmt, .cmt2, .cmt3"):
                    cmt_el.decompose()
                title = link.get_text(strip=True)
                if not title or len(title) < 3:
                    continue

                seen.add(origin_id)
                url = href if href.startswith("http") else BASE_URL + href
                posts.append({
                    "origin_id": origin_id,
                    "title": title,
                    "url": url,
                })

            log.info("Section '%s': %d new posts", section["name"], len(posts))

        log.info("Total unique posts from listing: %d", len(posts))
        return posts

    # ------------------------------------------------------------------
    # Post detail
    # ------------------------------------------------------------------

    def parse_post(self, url: str) -> dict:
        resp = self._get(url)
        soup = BeautifulSoup(resp.text, "html.parser")

        # 제목: span#nowsubject — .cmt 댓글 수 스팬 제거 후 추출
        # decompose 전에 .cmt 텍스트를 읽어야 댓글 수 보존 가능
        title_el = soup.select_one("#nowsubject")
        cmt_span = title_el.select_one(".cmt") if title_el else None
        _page_comments_count: int = self._parse_int(self._text(cmt_span)) if cmt_span else 0
        if title_el:
            for cmt_el in title_el.select(".cmt, .cmt2, .cmt3"):
                cmt_el.decompose()
            title = title_el.get_text(strip=True)
        else:
            title = ""

        # 본문: #memo_content_1 — 스크립트/버튼 제거 후 텍스트 추출
        # 이미지 전용 게시글은 텍스트가 없으므로 이미지 URL 목록으로 폴백
        content_el = soup.select_one("#memo_content_1") or soup.select_one(".memo_content")

        images: list[str] = []
        if content_el:
            for img in content_el.select("img"):
                src = img.get("src") or img.get("data-src") or ""
                if src.startswith("//"):
                    src = "https:" + src
                if src and src.startswith("http"):
                    images.append(src)
            # 추천수: .fan-option-button-group 내 b.votenow{no}에 pre-render됨
            # decompose 이전에 먼저 읽어야 함 (vote.php 직접 호출 미사용 — 투표 행위 위험)
            _votenow_el = content_el.select_one("b[class^='votenow']")
            likes: int = self._parse_int(self._text(_votenow_el)) if _votenow_el else 0
            # 스크립트·버튼 요소 제거 후 텍스트 추출
            for el in content_el.select("script, .fan-option-button-group"):
                el.decompose()
            content = content_el.get_text("\n", strip=True)
            # 이미지 전용 게시글: 텍스트가 없으면 이미지 URL 목록으로 대체
            if len(content) < 30 and images:
                content = "\n".join(images)
        else:
            content = ""
            likes = 0

        # 조회수: span#hit
        hit_el = soup.select_one("span#hit")
        views = self._parse_int(self._text(hit_el)) if hit_el else 0

        comments = self._parse_comments(soup)

        # 댓글 수: 제목 영역 .cmt span이 정적으로 렌더링됨 (decompose 전에 읽음)
        # (#ajax_comment 영역은 JS 로딩 → len(comments) 는 항상 0)
        comments_count = _page_comments_count or len(comments)

        time.sleep(0.3)

        return {
            "title": title,
            "content": content,
            "images": images or None,
            "stats": {
                "views": views,
                "likes": likes,
                "comments_count": comments_count,
            },
            "comments": comments,
        }

    # ------------------------------------------------------------------
    # Comments
    # ------------------------------------------------------------------

    def _parse_comments(self, soup: BeautifulSoup) -> list[dict]:
        results: list[dict] = []

        # 인스티즈 댓글 구조: #ajax_comment 내 tr.cmt_view
        # - 작성자: td.comment_memo .href
        # - 내용:   td.comment_memo .comment_line span[id^='n']
        # - 공감수: 정적 HTML에 노출 안 됨 → 0
        for row in soup.select("#ajax_comment tr.cmt_view"):
            memo_td = row.select_one("td.comment_memo")
            if not memo_td:
                continue

            author_el = memo_td.select_one(".href")
            # id가 'n'으로 시작하는 span이 댓글 본문
            body_el = memo_td.select_one("span[id^='n']")

            if not body_el:
                continue

            body = body_el.get_text(strip=True)
            # 로그인 안내 문구는 실제 댓글이 아님
            if not body or "로그인 후 이용" in body:
                continue

            results.append({
                "author": self._text(author_el) if author_el else "익명",
                "content": body,
                "likes": 0,
            })

        return results
