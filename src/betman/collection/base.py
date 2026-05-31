"""수집 레이어 인터페이스.

각 데이터 소스는 이 추상 클래스를 구현한다. 구현체를 교체하면(mock → 유료 API)
상위 레이어 코드는 그대로 둔 채 데이터 소스만 바꿀 수 있다.

원칙: 모든 외부 수집은 정식 API/허용된 피드만 사용한다. 무단 스크래핑 금지.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date

from ..domain.enums import Sport
from ..domain.features import MatchFeatures
from ..domain.models import (
    BetmanOffering,
    InjuryNote,
    Lineup,
    Match,
    NewsItem,
    OddsQuote,
)


class MatchCollector(ABC):
    """정형: 경기 일정 + 라인업 + 부상/결장.

    구현 예) mock / Sportradar / Opta(Stats Perform).
    """

    @abstractmethod
    def collect_matches(self, sport: Sport, target_date: date) -> list[Match]:
        """해당 종목/날짜의 경기 목록."""

    @abstractmethod
    def collect_injuries(self, match: Match) -> list[InjuryNote]:
        """경기의 부상/결장 정보."""

    @abstractmethod
    def collect_lineups(self, match: Match) -> list[Lineup]:
        """경기의 (예상)라인업."""


class OddsCollector(ABC):
    """정형: 여러 해외 북메이커의 배당 (참고용, 컨센서스 추정).

    구현 예) mock / The Odds API / OddsJam.
    """

    @abstractmethod
    def collect_odds(self, match: Match) -> list[OddsQuote]:
        """여러 북메이커 × 여러 선택지의 십진 배당."""


class BetmanCollector(ABC):
    """정형: 베트맨 발매 경기 + 고정배당 (실제 베팅 대상).

    구현 예) mock / 베트맨 공식 발매 데이터.
    """

    @abstractmethod
    def collect_offerings(self, match: Match) -> list[BetmanOffering]:
        """경기에 대한 베트맨 발매 항목. 미발매면 빈 리스트."""


class NewsCollector(ABC):
    """비정형: 뉴스/분석글 원문 (정식 API/허용 피드만).

    여기서는 원문(NewsItem)만 모은다. LLM 요약·감성분류는 3단계(분석)에서 수행.
    구현 예) mock / 뉴스 API / 허용된 RSS 피드.
    """

    @abstractmethod
    def collect_news(self, match: Match) -> list[NewsItem]:
        """경기 관련 비정형 원문."""


class FeatureCollector(ABC):
    """정형: 종목별 예측 변수(폼/h2h/일정/배당흐름 + 종목 핵심 변수).

    종목마다 결정적 변수가 다르므로(축구=xG·라인업, 야구=선발투수,
    농구=휴식·스타결장) 구현체가 종목에 맞는 블록을 채운다.
    값을 모르면 0으로 채우지 말고 Feature.missing 으로 결측을 명시할 것.

    구현 예) mock / 통계 API(폼·xG·파크팩터 등) + 배당 API(라인 무브먼트).
    """

    @abstractmethod
    def collect_features(self, match: Match) -> MatchFeatures:
        """경기에 대한 종목별 정규화 feature 묶음."""
