"""수집 소스 조립 (mock ↔ live 선택).

요청 사양:
  - "live" 모드: 해외 배당 = The Odds API, 뉴스 = RSS 피드 (실제 데이터)
  - mock 도 유지: 베트맨 발매·정형 통계는 공개 API가 없어 mock 사용,
    또한 mode="mock" 이면 전부 mock.

정직성: live 라도 베트맨 고정배당/통계 feature 는 mock 이다(실 API 부재).
The Odds API 가 미설정/실패하면 자동으로 mock 으로 폴백한다.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from ..config import (
    AppConfig,
    load_odds_api_settings,
    load_rss_settings,
)
from .. import env
from .base import (
    BetmanCollector,
    FeatureCollector,
    MatchCollector,
    NewsCollector,
    OddsCollector,
)
from .mock.mock_betman import MockBetmanCollector
from .mock.mock_features import MockFeatureCollector
from .mock.mock_match import MockMatchCollector
from .mock.mock_news import MockNewsCollector
from .mock.mock_odds import MockOddsCollector


@dataclass
class CollectorSet:
    match: MatchCollector
    odds: OddsCollector
    betman: BetmanCollector
    news: NewsCollector
    features: FeatureCollector
    notes: list[str]            # 어떤 소스가 실/모의인지 사람이 읽는 메모


def build_collectors(config: AppConfig) -> CollectorSet:
    """config.data_source_mode 에 따라 5개 수집기를 조립."""
    notes: list[str] = []
    env.load_dotenv()

    # 통계 feature 는 항상 mock (실 API 부재)
    features = MockFeatureCollector()

    # 베트맨 발매: BETMAN_SOURCE=csv 면 수동 입력 CSV/JSON, 아니면 mock
    betman: BetmanCollector
    if (os.environ.get("BETMAN_SOURCE") or "").lower() == "csv":
        from .live.betman_csv import BetmanCsvCollector

        src_dir = os.environ.get("BETMAN_DIR", "data/betman")
        betman = BetmanCsvCollector(source_dir=src_dir)
        notes.append(f"베트맨 발매: CSV 수동 입력 ({src_dir}) | 통계: mock")
    else:
        betman = MockBetmanCollector()
        notes.append("베트맨 발매/통계 feature: mock (공개 API 없음)")

    if config.data_source_mode != "live":
        notes.append("모드=mock: 전 수집기 mock")
        return CollectorSet(
            match=MockMatchCollector(),
            odds=MockOddsCollector(),
            betman=betman,
            news=MockNewsCollector(),
            features=features,
            notes=notes,
        )

    # live 모드 ----------------------------------------------------------
    match: MatchCollector = MockMatchCollector()
    odds: OddsCollector = MockOddsCollector()
    news: NewsCollector = MockNewsCollector()

    # 해외 배당 + 경기 목록: The Odds API
    odds_settings = load_odds_api_settings()
    if odds_settings.configured:
        try:
            from .live.odds_api import (
                OddsApiClient,
                OddsApiMatchCollector,
                OddsApiOddsCollector,
            )

            client = OddsApiClient(odds_settings)
            match = OddsApiMatchCollector(client)
            odds = OddsApiOddsCollector(client)
            notes.append(
                f"해외 배당+경기: The Odds API (regions={odds_settings.regions})"
            )
        except Exception as e:  # noqa: BLE001
            notes.append(f"The Odds API 폴백→mock ({type(e).__name__}: {e})")
    else:
        notes.append("ODDS_API_KEY 없음 → 배당/경기 mock 폴백")

    # 뉴스: RSS 피드 (피드가 설정된 종목만 실데이터)
    rss_settings = load_rss_settings()
    if rss_settings.feeds:
        from .live.rss_news import RssNewsCollector

        news = RssNewsCollector(rss_settings)
        sports = ", ".join(s.value for s in rss_settings.feeds)
        notes.append(f"뉴스: RSS 피드 ({sports})")
    else:
        notes.append("RSS_FEEDS_* 없음 → 뉴스 mock 폴백")

    return CollectorSet(match, odds, betman, news, features, notes)
