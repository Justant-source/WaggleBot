"""
Crawler Plugin Manager

크롤러 등록 및 관리 시스템
"""

import logging
from typing import Dict, Type, List

from crawlers.base import BaseCrawler

log = logging.getLogger(__name__)


class CrawlerRegistry:
    """크롤러 플러그인 레지스트리"""

    _crawlers: Dict[str, Type[BaseCrawler]] = {}
    _metadata: Dict[str, dict] = {}

    @classmethod
    def register(cls, site_code: str, **metadata):
        """크롤러 등록 데코레이터.

        Args:
            site_code: 사이트 코드 (예: 'nate_pann', 'bobaedream')
            **metadata: 추가 메타데이터 (description, enabled 등)

        Example:
            @CrawlerRegistry.register('nate_pann', description='네이트판 크롤러')
            class NatePannCrawler(BaseCrawler):
                pass
        """
        def decorator(crawler_class: Type[BaseCrawler]):
            if not issubclass(crawler_class, BaseCrawler):
                raise TypeError(
                    f"{crawler_class.__name__} must inherit from BaseCrawler"
                )

            cls._crawlers[site_code] = crawler_class
            cls._metadata[site_code] = {
                'class_name': crawler_class.__name__,
                'module': crawler_class.__module__,
                'description': metadata.get('description', ''),
                'enabled': metadata.get('enabled', True),
                **metadata
            }

            log.debug("Registered crawler: %s -> %s", site_code, crawler_class.__name__)
            return crawler_class

        return decorator

    @classmethod
    def get_crawler(cls, site_code: str) -> BaseCrawler:
        """사이트 코드로 크롤러 인스턴스 반환.

        Raises:
            ValueError: 등록되지 않은 사이트 코드
        """
        if site_code not in cls._crawlers:
            available = ", ".join(cls._crawlers.keys())
            raise ValueError(
                f"Unknown site code: '{site_code}'. Available: {available}"
            )
        return cls._crawlers[site_code]()

    @classmethod
    def list_crawlers(cls) -> List[dict]:
        """등록된 모든 크롤러 목록 반환."""
        result = []
        for site_code, crawler_class in cls._crawlers.items():
            metadata = cls._metadata.get(site_code, {})
            result.append({
                'site_code': site_code,
                'class_name': crawler_class.__name__,
                'module': crawler_class.__module__,
                'description': metadata.get('description', ''),
                'enabled': metadata.get('enabled', True),
            })
        return result

    @classmethod
    def get_enabled_crawlers(cls) -> List[str]:
        """활성화된 크롤러 코드 목록 반환."""
        return [
            site_code for site_code, meta in cls._metadata.items()
            if meta.get('enabled', True)
        ]

    @classmethod
    def is_registered(cls, site_code: str) -> bool:
        """사이트 코드가 등록되어 있는지 확인."""
        return site_code in cls._crawlers

    @classmethod
    def unregister(cls, site_code: str) -> bool:
        """특정 크롤러 등록 해제 (테스트용)."""
        if site_code in cls._crawlers:
            del cls._crawlers[site_code]
            cls._metadata.pop(site_code, None)
            return True
        return False

    @classmethod
    def clear(cls) -> None:
        """레지스트리 전체 초기화 (테스트용)."""
        cls._crawlers.clear()
        cls._metadata.clear()


# ===========================================================================
# 편의 함수
# ===========================================================================

def get_crawler(site_code: str) -> BaseCrawler:
    """크롤러 인스턴스 반환 (편의 함수)."""
    return CrawlerRegistry.get_crawler(site_code)


def list_crawlers() -> List[dict]:
    """등록된 크롤러 목록 반환 (편의 함수)."""
    return CrawlerRegistry.list_crawlers()


def auto_discover(package: str) -> int:
    """패키지를 스캔하여 크롤러를 자동 발견·등록한다.

    @CrawlerRegistry.register() 데코레이터를 재실행하기 위해
    이미 임포트된 모듈은 reload한다.

    Returns:
        발견된 크롤러 수
    """
    import importlib
    import pkgutil
    import sys

    try:
        pkg = importlib.import_module(package)
    except ImportError:
        log.warning("auto_discover: 패키지 '%s' 로드 실패", package)
        return 0

    # base.py · plugin_manager.py는 제외 — reload 시 BaseCrawler 클래스 객체가
    # 새로 생성돼 issubclass 체크가 실패하므로
    _SKIP = {"base", "plugin_manager"}

    for _, module_name, is_pkg in pkgutil.iter_modules(pkg.__path__):
        if module_name.startswith('_') or is_pkg or module_name in _SKIP:
            continue
        full_name = f"{package}.{module_name}"
        try:
            if full_name in sys.modules:
                importlib.reload(sys.modules[full_name])
            else:
                importlib.import_module(full_name)
        except Exception as e:
            log.debug("auto_discover: '%s' 로드 실패: %s", full_name, e)

    return len(CrawlerRegistry._crawlers)
