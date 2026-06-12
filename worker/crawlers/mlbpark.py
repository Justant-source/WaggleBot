import logging
import re
import time
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from crawlers.base import BaseCrawler
from crawlers.plugin_manager import CrawlerRegistry

log = logging.getLogger(__name__)

BASE_URL = "https://mlbpark.donga.com"
BOARD_URL = f"{BASE_URL}/mlbpark/b.php"


@CrawlerRegistry.register(
    "mlbpark",
    description="MLB파크 불펜 인기글 크롤러",
    enabled=True,
)
class MlbparkCrawler(BaseCrawler):
    site_code = "mlbpark"
    SECTIONS = [
        {"name": "불펜 (종합)", "url": f"{BOARD_URL}?b=bullpen"},
        {"name": "자유게시판", "url": f"{BOARD_URL}?b=bullpen2"},
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

            # MLB파크 게시판: table.bd_list 내 tr — id= 파라미터로 게시글 식별
            _id_pat = re.compile(r"id=(\d+)")
            for link in soup.select("table.bd_list td.title a, table tr td.tit a"):
                href = link.get("href", "")
                m = _id_pat.search(href)
                if not m:
                    continue

                origin_id = m.group(1)
                if origin_id in seen:
                    continue

                title = link.get_text(strip=True)
                if not title or len(title) < 2:
                    continue

                seen.add(origin_id)
                full_url = href if href.startswith("http") else urljoin(BASE_URL, href)
                posts.append({
                    "origin_id": origin_id,
                    "title": title,
                    "url": full_url,
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

        title = self._text(
            soup.select_one("h2.view_tit, .article_tit h2, .view_title")
        )

        content_el = soup.select_one(".view_textbody, .article_body, .bd_view_contents")
        content = content_el.get_text("\n", strip=True) if content_el else ""

        images: list[str] = []
        if content_el:
            for img in content_el.select("img"):
                src = img.get("src") or img.get("data-src") or ""
                if src and src.startswith("http"):
                    images.append(src)

        page_text = soup.get_text()
        views = self._parse_stat(page_text, r"조회\s*:?\s*([\d,]+)")
        likes = self._parse_stat(page_text, r"추천\s*:?\s*([\d,]+)")

        comments = self._parse_comments(soup)

        time.sleep(0.3)

        return {
            "title": title,
            "content": content,
            "images": images or None,
            "stats": {
                "views": views,
                "likes": likes,
                "comments_count": len(comments),
            },
            "comments": comments,
        }

    # ------------------------------------------------------------------
    # Comments
    # ------------------------------------------------------------------

    def _parse_comments(self, soup: BeautifulSoup) -> list[dict]:
        results: list[dict] = []

        # MLB파크 댓글: .comment_list 또는 .reply_list 내 항목
        for item in soup.select(".comment_list li, .reply_wrap li, .cmtlist li"):
            author_el = item.select_one(".nick, .comment_nick, .user_id")
            body_el = item.select_one(".comment_view, .reply_txt, .cmttext")
            likes_el = item.select_one(".ok_cnt, .like_count, .vote_ok")

            if not body_el:
                continue

            body = body_el.get_text(strip=True)
            if not body:
                continue

            results.append({
                "author": self._text(author_el) if author_el else "익명",
                "content": body,
                "likes": self._parse_int(self._text(likes_el)) if likes_el else 0,
            })

        return results
