import logging
import re
import time

import requests
from bs4 import BeautifulSoup

from crawlers.base import BaseCrawler
from crawlers.plugin_manager import CrawlerRegistry

log = logging.getLogger(__name__)

BASE_URL = "https://theqoo.net"


@CrawlerRegistry.register(
    "theqoo",
    description="더쿠 인기글(HOT) 크롤러",
    enabled=True,
)
class TheqooCrawler(BaseCrawler):
    site_code = "theqoo"
    SECTIONS = [
        {"name": "HOT 게시판", "url": f"{BASE_URL}/hot"},
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

            # 더쿠 XE 구조: table.bd_lst 내 각 tr에 a[href*="document_srl"] 링크
            _href_pat = re.compile(r"document_srl=(\d+)|/hot/(\d+)")
            for link in soup.find_all("a", href=_href_pat):
                href = link.get("href", "")
                m = _href_pat.search(href)
                if not m:
                    continue

                origin_id = m.group(1) or m.group(2)
                if not origin_id or origin_id in seen:
                    continue

                title = link.get_text(strip=True)
                # 제목 없는 아이콘·이미지 링크 제외
                if not title or len(title) < 2:
                    continue

                # 숫자만인 경우(페이지네이션 링크) 제외
                if title.isdigit():
                    continue

                seen.add(origin_id)
                url = (
                    href if href.startswith("http")
                    else BASE_URL + href
                )
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

        # XE 표준 구조
        title = self._text(
            soup.select_one("h1.np_18px_span, .document_title, #bd_main h1")
        )

        content_el = soup.select_one(".xe_content, .document_contents, .rd_body")
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

        # XE 댓글: #comment_list 내 li.comment 또는 .comment_item
        for item in soup.select("#comment_list .comment, .comment_list li"):
            author_el = item.select_one(".comment_author, .nick, .member_info strong")
            body_el = item.select_one(".comment_content .xe_content, .comment_text, .xe_content")
            likes_el = item.select_one(".comment_like_wrap .count, .vote_up .count")

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
