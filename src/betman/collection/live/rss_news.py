"""RSS 피드 기반 뉴스 수집 (정식/허용 피드만, 무단 스크래핑 금지).

RSS 2.0(<item>) 과 Atom(<entry>) 을 모두 파싱한다. 표준 라이브러리만 사용.
경기별로는 제목/본문에 양 팀 이름이 들어간 항목만 골라 NewsItem 으로 반환한다.

피드는 종목별로 config.RssSettings.feeds 또는 .env(RSS_FEEDS_<SPORT>)로 주입.
피드를 한 번 받아 캐시하므로 같은 종목의 여러 경기에서 재요청하지 않는다.
"""

from __future__ import annotations

import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree as ET

from ...config import RssSettings, load_rss_settings
from ...domain.enums import Sport
from ...domain.models import Match, NewsItem
from ..base import NewsCollector

_ATOM = "{http://www.w3.org/2005/Atom}"


def _text(el) -> str:
    return (el.text or "").strip() if el is not None else ""


def _parse_date(s: str) -> datetime:
    if not s:
        return datetime.now(timezone.utc)
    try:
        return parsedate_to_datetime(s)  # RSS pubDate (RFC822)
    except (TypeError, ValueError):
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00"))  # Atom
        except ValueError:
            return datetime.now(timezone.utc)


def parse_feed(xml_bytes: bytes, source: str) -> list[NewsItem]:
    """RSS/Atom 바이트 → NewsItem 목록."""
    items: list[NewsItem] = []
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return items

    # RSS 2.0: channel/item
    for item in root.iter("item"):
        items.append(
            NewsItem(
                source=source,
                title=_text(item.find("title")),
                body=_text(item.find("description")),
                published_at=_parse_date(_text(item.find("pubDate"))),
                url=_text(item.find("link")),
            )
        )
    # Atom: entry
    for entry in root.iter(f"{_ATOM}entry"):
        link_el = entry.find(f"{_ATOM}link")
        url = link_el.get("href") if link_el is not None else ""
        items.append(
            NewsItem(
                source=source,
                title=_text(entry.find(f"{_ATOM}title")),
                body=_text(entry.find(f"{_ATOM}summary")),
                published_at=_parse_date(_text(entry.find(f"{_ATOM}updated"))),
                url=url or "",
            )
        )
    return items


class RssNewsCollector(NewsCollector):
    """종목별 RSS 피드를 받아 경기(팀명 매칭)별 뉴스를 반환."""

    def __init__(self, settings: RssSettings | None = None) -> None:
        self.settings = settings or load_rss_settings()
        # feed_url -> (fetched_at, items)
        self._cache: dict[str, tuple[float, list[NewsItem]]] = {}

    def _fetch_feed(self, url: str) -> list[NewsItem]:
        cached = self._cache.get(url)
        now = time.time()
        if cached and now - cached[0] < 600:
            return cached[1]
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "betman-analyzer/0.1 (+rss)"}
            )
            with urllib.request.urlopen(req, timeout=self.settings.timeout_sec) as r:
                data = r.read()
        except (urllib.error.URLError, TimeoutError, OSError):
            self._cache[url] = (now, [])
            return []
        items = parse_feed(data, source=url)[: self.settings.max_items_per_feed]
        self._cache[url] = (now, items)
        return items

    def collect_news(self, match: Match) -> list[NewsItem]:
        feeds = self.settings.feeds.get(match.sport, [])
        if not feeds:
            return []
        home, away = match.home.name, match.away.name
        out: list[NewsItem] = []
        for url in feeds:
            for item in self._fetch_feed(url):
                text = f"{item.title} {item.body}"
                if home in text or away in text:
                    out.append(item)
        return out
