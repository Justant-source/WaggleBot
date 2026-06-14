import json
import logging
import re
import time

import requests
from bs4 import BeautifulSoup

from crawlers.base import BaseCrawler
from crawlers.plugin_manager import CrawlerRegistry

log = logging.getLogger(__name__)

BASE_URL = "https://theqoo.net"
_COMMENT_API_ACT = "dispTheqooContentCommentListTheqoo"


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
            section_count = 0

            # 더쿠 Rhymix 구조: tbody 행 단위 순회, 공지(tr.notice) 제외
            _href_pat = re.compile(r"document_srl=(\d+)|/hot/(\d+)")
            for row in soup.select("table tbody tr"):
                # 공지글 제외 — tr class에 'notice' 포함 행 건너뜀
                if "notice" in " ".join(row.get("class") or []):
                    continue

                link = row.select_one("a[href*='/hot/']")
                if not link:
                    continue

                href = link.get("href", "")
                # 앵커 링크(댓글 수) 제외: /hot/123#123_comment
                if "#" in href:
                    continue
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
                # 숫자만인 경우(댓글 수·페이지 번호 링크) 제외
                if title.isdigit():
                    continue

                seen.add(origin_id)
                url = href if href.startswith("http") else BASE_URL + href
                # page 파라미터 제거 (?page=N)
                url = re.sub(r"\?page=\d+", "", url)
                posts.append({
                    "origin_id": origin_id,
                    "title": title,
                    "url": url,
                })
                section_count += 1

            log.info("Section '%s': %d new posts (공지 제외)", section["name"], section_count)

        log.info("Total unique posts from listing: %d", len(posts))
        return posts

    # ------------------------------------------------------------------
    # Post detail
    # ------------------------------------------------------------------

    def parse_post(self, url: str) -> dict:
        resp = self._get(url)
        soup = BeautifulSoup(resp.text, "html.parser")

        # 제목: .theqoo_document_header .title
        title = self._text(soup.select_one(".theqoo_document_header .title"))

        # 본문: .xe_content
        content_el = soup.select_one(".xe_content")
        content = content_el.get_text("\n", strip=True) if content_el else ""

        images: list[str] = []
        if content_el:
            for img in content_el.select("img"):
                src = img.get("src") or img.get("data-src") or ""
                if src and src.startswith("http"):
                    images.append(src)

        # 통계: .theqoo_document_header .count_container
        # 구조: <i class="far fa-eye"></i> 22,233 <i class="far fa-comment-dots"></i> 146
        views = 0
        comments_count_from_page = 0
        count_el = soup.select_one(".theqoo_document_header .count_container")
        if count_el:
            nums = re.findall(r"[\d,]+", count_el.get_text(" ", strip=True))
            if len(nums) >= 1:
                views = self._parse_int(nums[0])
            if len(nums) >= 2:
                comments_count_from_page = self._parse_int(nums[1])

        # CSRF 토큰 추출 (댓글 API 인증용)
        csrf_token = ""
        csrf_el = soup.select_one("meta[name=csrf-token]")
        if csrf_el:
            csrf_token = csrf_el.get("content", "")

        # document_srl 추출
        doc_srl = self._extract_doc_srl(url, soup)

        comments: list[dict] = []
        if doc_srl:
            comments = self._fetch_comments(doc_srl, csrf_token, url)

        time.sleep(0.3)

        return {
            "title": title,
            "content": content,
            "images": images or None,
            "stats": {
                "views": views,
                "likes": 0,  # 더쿠는 추천/좋아요 기능 없음
                "comments_count": len(comments) or comments_count_from_page,
            },
            "comments": comments,
        }

    # ------------------------------------------------------------------
    # Comments (AJAX API)
    # ------------------------------------------------------------------

    def _extract_doc_srl(self, url: str, soup: BeautifulSoup) -> str:
        """URL 또는 페이지에서 document_srl 추출."""
        # URL에서 추출: /hot/4241291747
        m = re.search(r"/hot/(\d+)", url)
        if m:
            return m.group(1)
        # document_srl 쿼리 파라미터
        m = re.search(r"document_srl=(\d+)", url)
        if m:
            return m.group(1)
        # loadReply 호출에서 추출
        for script in soup.find_all("script"):
            if script.string:
                m = re.search(r"loadReply\((\d+)", script.string)
                if m:
                    return m.group(1)
        return ""

    def _fetch_comments(
        self, doc_srl: str, csrf_token: str, referer_url: str
    ) -> list[dict]:
        """더쿠 댓글 AJAX API 호출.

        비회원은 작성 후 1시간 이내 댓글을 볼 수 없으므로, 오래된 게시글에서만
        실제 내용이 반환됩니다. 최신 게시글은 빈 목록이 반환될 수 있습니다.
        """
        results: list[dict] = []
        payload = {
            "act": _COMMENT_API_ACT,
            "document_srl": int(doc_srl),
            "cpage": 0,
        }
        headers_extra = {
            "Content-Type": "application/json; charset=utf-8",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": referer_url,
        }

        try:
            resp = self._session.post(
                f"{BASE_URL}/index.php",
                data=json.dumps(payload),
                headers=headers_extra,
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            log.debug("댓글 API 실패 (document_srl=%s)", doc_srl)
            return results

        for item in data.get("comment_list", []):
            ct_html = item.get("ct", "")
            ct_soup = BeautifulSoup(ct_html, "html.parser")
            body = ct_soup.get_text(strip=True)

            # 비회원 차단 메시지 제외
            if not body or "비회원은 작성한 지" in body:
                continue

            # ind: 들여쓰기(대댓글 depth). -1은 일반 댓글, 양수는 대댓글
            results.append({
                "author": "익명",  # 더쿠는 비회원 게시판 — 닉네임 없음
                "content": body,
                "likes": 0,  # ind는 들여쓰기 레벨이므로 좋아요 수 없음
            })

        return results
