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

            # 인스티즈 인기글 목록: .board_wrap 내 .stext 링크
            for link in soup.select("a[href*='/pt/']"):
                href = link.get("href", "")
                m = re.search(r"/pt/(\d+)", href)
                if not m:
                    continue

                origin_id = m.group(1)
                if origin_id in seen:
                    continue

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

        title = self._text(soup.select_one(".memo_subject") or soup.select_one("h2.title"))

        content_el = soup.select_one(".memo_content") or soup.select_one(".content_view")
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

        # 인스티즈 댓글 구조: .comment_wrap 또는 .cmt_wrap
        for item in soup.select(".comment_wrap .comment_list li, .cmt_list li"):
            author_el = item.select_one(".id_info, .comment_id, .nick")
            body_el = item.select_one(".comment_memo, .cmt_memo, .cmt_text")
            likes_el = item.select_one(".ok_num, .vote_btn_cnt, .like_cnt")

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
