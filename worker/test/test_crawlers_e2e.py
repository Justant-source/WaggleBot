"""
Crawler E2E Test — 모든 크롤러의 listing/parse_post/댓글 수집을 실제 네트워크로 검증.

실행: docker exec env-crawler-1 python -m test.test_crawlers_e2e
"""

import logging
import sys
import traceback
from dataclasses import dataclass, field

import crawlers  # noqa: F401 — 모든 크롤러 @register 실행
from crawlers.plugin_manager import CrawlerRegistry

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

ALL_CRAWLERS = [
    "nate_pann",
    "bobaedream",
    "dcinside",
    "fmkorea",
    "instiz",
    "theqoo",
    "mlbpark",
]

REQUIRED_LISTING_KEYS = {"origin_id", "title", "url"}
REQUIRED_DETAIL_KEYS  = {"title", "content", "stats", "comments"}
REQUIRED_STAT_KEYS    = {"views", "likes", "comments_count"}
REQUIRED_COMMENT_KEYS = {"author", "content"}


@dataclass
class CrawlerResult:
    site_code: str
    listing_count: int = 0
    listing_errors: list[str] = field(default_factory=list)
    detail_ok: bool = False
    detail_errors: list[str] = field(default_factory=list)
    detail_sample: dict = field(default_factory=dict)
    fatal: str = ""


def check_listing(result: CrawlerResult, crawler) -> list[dict]:
    """fetch_listing 검증 — 필드 존재·타입 확인."""
    try:
        listings = crawler.fetch_listing()
    except Exception as e:
        result.fatal = f"fetch_listing() 예외: {e}\n{traceback.format_exc()}"
        return []

    result.listing_count = len(listings)
    if not listings:
        result.listing_errors.append("listing 결과가 0건")
        return []

    for i, item in enumerate(listings[:3]):
        missing = REQUIRED_LISTING_KEYS - item.keys()
        if missing:
            result.listing_errors.append(f"[{i}] 필드 누락: {missing}")
        if not str(item.get("origin_id", "")).strip():
            result.listing_errors.append(f"[{i}] origin_id 비어있음")
        if not str(item.get("url", "")).startswith("http"):
            result.listing_errors.append(f"[{i}] url 이상: {item.get('url')!r}")

    return listings


def check_detail(result: CrawlerResult, crawler, url: str) -> None:
    """parse_post 검증 — 필드·내용 확인."""
    try:
        detail = crawler.parse_post(url)
    except Exception as e:
        result.detail_errors.append(f"parse_post() 예외: {e}\n{traceback.format_exc()}")
        return

    result.detail_sample = {k: v for k, v in detail.items() if k != "content"}

    # 필수 키
    missing = REQUIRED_DETAIL_KEYS - detail.keys()
    if missing:
        result.detail_errors.append(f"필드 누락: {missing}")

    # title
    if not detail.get("title", "").strip():
        result.detail_errors.append("title 비어있음")

    # content
    content = detail.get("content") or ""
    if len(content) < 30:
        result.detail_errors.append(f"content 짧음 ({len(content)}자 < 30자): {content!r}")

    # stats
    stats = detail.get("stats") or {}
    missing_stats = REQUIRED_STAT_KEYS - stats.keys()
    if missing_stats:
        result.detail_errors.append(f"stats 필드 누락: {missing_stats}")
    for k in REQUIRED_STAT_KEYS - missing_stats:
        if not isinstance(stats.get(k), (int, float)):
            result.detail_errors.append(f"stats.{k} 타입 이상: {stats.get(k)!r}")

    # comments
    comments = detail.get("comments") or []
    if not isinstance(comments, list):
        result.detail_errors.append(f"comments 타입 이상: {type(comments)}")
    else:
        for j, c in enumerate(comments[:3]):
            missing_c = REQUIRED_COMMENT_KEYS - c.keys()
            if missing_c:
                result.detail_errors.append(f"comment[{j}] 필드 누락: {missing_c}")
            if not c.get("author", "").strip():
                result.detail_errors.append(f"comment[{j}] author 비어있음")
            if not c.get("content", "").strip():
                result.detail_errors.append(f"comment[{j}] content 비어있음")

    result.detail_ok = not result.detail_errors


def run_crawler_e2e(site_code: str) -> CrawlerResult:
    result = CrawlerResult(site_code=site_code)
    log.info("━" * 60)
    log.info("▶ [%s] 테스트 시작", site_code)

    try:
        crawler = CrawlerRegistry.get_crawler(site_code)
    except Exception as e:
        result.fatal = f"get_crawler() 실패: {e}"
        return result

    listings = check_listing(result, crawler)
    if result.fatal or not listings:
        return result

    log.info("  listing: %d건 수집", result.listing_count)

    # 첫 번째 글로 상세 파싱
    first_url = listings[0]["url"]
    log.info("  parse_post: %s", first_url)
    check_detail(result, crawler, first_url)

    return result


def print_report(results: list[CrawlerResult]) -> bool:
    """결과 출력 및 성공 여부 반환."""
    log.info("\n" + "=" * 60)
    log.info("E2E 테스트 결과 요약")
    log.info("=" * 60)

    all_pass = True
    for r in results:
        issues = r.listing_errors + r.detail_errors
        if r.fatal:
            issues = [r.fatal]

        status = "✅ PASS" if (not issues and r.listing_count > 0 and r.detail_ok) else "❌ FAIL"
        if status.startswith("❌"):
            all_pass = False

        log.info("")
        log.info("%s  [%s]  listing=%d건  detail=%s",
                 status, r.site_code, r.listing_count,
                 "OK" if r.detail_ok else "FAIL")

        if r.detail_sample:
            stats = r.detail_sample.get("stats", {})
            comments = r.detail_sample.get("comments", [])
            log.info("      title   : %s", r.detail_sample.get("title", "")[:60])
            log.info("      stats   : views=%s likes=%s comments=%s",
                     stats.get("views"), stats.get("likes"), stats.get("comments_count"))
            log.info("      comments: %d개", len(comments) if isinstance(comments, list) else 0)
            if r.detail_sample.get("images"):
                log.info("      images  : %d개", len(r.detail_sample["images"]))

        for issue in issues[:5]:
            log.warning("      ⚠ %s", issue.split("\n")[0])

    log.info("")
    log.info("=" * 60)
    if all_pass:
        log.info("✅ 모든 크롤러 통과")
    else:
        failed = [r.site_code for r in results
                  if r.fatal or r.listing_errors or not r.detail_ok or r.listing_count == 0]
        log.error("❌ 실패한 크롤러: %s", failed)
    log.info("=" * 60)

    return all_pass


def main() -> None:
    log.info("크롤러 E2E 테스트 시작 (대상: %s)", ALL_CRAWLERS)
    results = [run_crawler_e2e(site) for site in ALL_CRAWLERS]
    passed = print_report(results)
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
