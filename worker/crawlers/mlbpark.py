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

            # MLB파크 게시판: table.tbl_type01 내 td.t_left — id= 파라미터로 게시글 식별
            _id_pat = re.compile(r"id=(\d+)")
            for link in soup.select("table.tbl_type01 td.t_left a"):
                href = link.get("href", "")
                m = _id_pat.search(href)
                if not m:
                    continue

                origin_id = m.group(1)
                if origin_id in seen:
                    continue

                # 댓글 수 스팬([289] 등) 제거 후 제목 추출
                for span in link.select("span.replycnt"):
                    span.decompose()
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

        # 제목: div.titles
        title = self._text(soup.select_one("div.titles"))

        # 본문: div.view_context
        content_el = soup.select_one("div.view_context")
        content = content_el.get_text("\n", strip=True) if content_el else ""

        images: list[str] = []
        if content_el:
            for img in content_el.select("img"):
                src = img.get("src") or img.get("data-src") or ""
                if src and src.startswith("http"):
                    images.append(src)

        # 조회/추천: ul.view_head 내 텍스트에서 추출
        view_head = soup.select_one("ul.view_head")
        head_text = view_head.get_text() if view_head else soup.get_text()
        views = self._parse_stat(head_text, r"조회\s*:?\s*([\d,]+)")
        likes = self._parse_stat(head_text, r"추천\s*:?\s*([\d,]+)")

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

        # MLB파크 댓글: div.reply_list > div.other_con|my_con > div.txt_box > div.txt
        reply_list = soup.select_one("div.reply_list")
        if not reply_list:
            return results

        for item in reply_list.select("div.other_con, div.my_con"):
            txt_div = item.select_one("div.txt_box div.txt")
            if not txt_div:
                continue

            author_el = txt_div.select_one("span.name")
            body_el = txt_div.select_one("span.re_txt")

            if not body_el:
                continue

            body = body_el.get_text(strip=True)
            if not body:
                continue

            results.append({
                "author": self._text(author_el) if author_el else "익명",
                "content": body,
                "likes": 0,
            })

        return results
