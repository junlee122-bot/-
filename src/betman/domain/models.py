"""종목 공통 정규화 데이터 모델.

수집 레이어의 모든 소스(정형/비정형, 국내/해외)는 최종적으로 이 모델들로
변환됩니다. 분석·저장·출력 레이어는 이 모델만 알면 됩니다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, date
from typing import TYPE_CHECKING

from .enums import (
    MarketType,
    MatchStatus,
    Outcome,
    SignalPolarity,
    Sport,
)

if TYPE_CHECKING:
    from .features import MatchFeatures


# --------------------------------------------------------------------------- #
# 정형 — 경기 / 팀 / 통계
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Team:
    id: str
    name: str
    sport: Sport


@dataclass(frozen=True)
class Match:
    """하나의 경기. 모든 소스가 같은 match_id 로 묶일 수 있도록 정규화한다."""

    id: str
    sport: Sport
    league: str
    home: Team
    away: Team
    start_time: datetime
    status: MatchStatus = MatchStatus.SCHEDULED


@dataclass(frozen=True)
class TeamRecord:
    """저장 레이어에 누적되는 팀별 전적(홈/원정 분리)."""

    team_id: str
    sport: Sport
    venue: str            # "home" | "away" | "overall"
    wins: int = 0
    draws: int = 0
    losses: int = 0

    @property
    def games(self) -> int:
        return self.wins + self.draws + self.losses

    @property
    def win_rate(self) -> float:
        return self.wins / self.games if self.games else 0.0


@dataclass(frozen=True)
class InjuryNote:
    """부상/결장 정보 (정형)."""

    team_id: str
    player_name: str
    status: str          # "out" | "doubtful" | "questionable" ...
    note: str = ""


@dataclass(frozen=True)
class Lineup:
    team_id: str
    confirmed: bool
    players: tuple[str, ...] = ()


# --------------------------------------------------------------------------- #
# 배당 — 해외(참고용) / 베트맨(실제 베팅 대상)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class OddsQuote:
    """해외 북메이커 하나가 제시한, 한 선택지에 대한 십진 배당.

    실제 베팅에는 쓰지 않으며 컨센서스 확률 추정에만 사용한다.
    """

    bookmaker: str
    market: MarketType
    outcome: Outcome
    decimal_odds: float
    captured_at: datetime

    @property
    def implied_prob(self) -> float:
        """마진 포함 내재확률 (1 / 배당). de-vig은 분석 레이어에서."""
        return 1.0 / self.decimal_odds if self.decimal_odds > 0 else 0.0


@dataclass(frozen=True)
class BetmanOffering:
    """베트맨 발매 항목 + 고정배당. 실제 베팅 대상.

    line: 핸디캡/언더오버의 기준점. 핸디캡은 홈 기준(예: H-1.0 → -1.0,
    소수핸디캡 H-3.5 → -3.5). 언더오버는 총점 기준선(예: U/O 2.5 → 2.5).
    1X2/머니라인/SUM 은 None.
    """

    match_id: str
    round_no: str                 # 베트맨 회차
    market: MarketType
    outcome: Outcome
    fixed_odds: float
    sales_open: bool = True       # 발매 중 여부
    line: float | None = None     # 핸디캡/언오버 기준점, 그 외 None
    game_no: str = ""             # 베트맨 게임번호(참고)


# --------------------------------------------------------------------------- #
# 비정형 — 뉴스/분석글 → (LLM 처리 후) 신호 플래그
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class NewsItem:
    """정식 API/허용된 피드로 수집한 비정형 원문 (LLM 입력용)."""

    source: str
    title: str
    body: str
    published_at: datetime
    url: str = ""


@dataclass(frozen=True)
class SentimentFlag:
    """LLM이 NewsItem을 요약·감성분류해 정형화한 '경기별 신호'.

    분석 레이어에서 value 점수의 보조 가중치로 사용된다.
    (수집 단계에서는 원문 NewsItem만 모으고, 이 플래그는 3단계 LLM이 채운다.)
    """

    target_outcome: Outcome       # 이 신호가 우호적/불리한 선택지
    polarity: SignalPolarity
    confidence: float             # 0.0 ~ 1.0
    summary: str
    source_url: str = ""


# --------------------------------------------------------------------------- #
# 정규화 결과 — 한 경기에 대한 모든 정보 묶음
# --------------------------------------------------------------------------- #
@dataclass
class NormalizedMatchBundle:
    """한 경기에 대해 4개 수집기가 모은 정보를 종목 공통 포맷으로 묶은 것.

    저장/분석/출력 레이어로 넘어가는 표준 단위.
    """

    match: Match
    betman_offerings: list[BetmanOffering] = field(default_factory=list)
    overseas_odds: list[OddsQuote] = field(default_factory=list)
    injuries: list[InjuryNote] = field(default_factory=list)
    lineups: list[Lineup] = field(default_factory=list)
    news: list[NewsItem] = field(default_factory=list)
    # 3단계(LLM)에서 news → sentiment_flags 로 채워짐
    sentiment_flags: list[SentimentFlag] = field(default_factory=list)
    # 종목별 예측 변수(정형). FeatureCollector가 채운다.
    features: "MatchFeatures | None" = None

    @property
    def has_betman(self) -> bool:
        """베트맨에 실제 발매된 경기인지 (발매 안 됐으면 분석/베팅 대상 아님)."""
        return any(o.sales_open for o in self.betman_offerings)

    @property
    def overseas_bookmaker_count(self) -> int:
        return len({q.bookmaker for q in self.overseas_odds})


@dataclass
class CollectionRequest:
    """수집 파이프라인 입력 — 어떤 종목/날짜를 모을지."""

    sports: list[Sport]
    target_date: date
