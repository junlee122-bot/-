"""종목 공통 열거형.

새로운 종목/마켓을 추가할 때 여기만 확장하면 수집·분석·출력이 모두 따라갑니다.
"""

from __future__ import annotations

from enum import Enum


class Sport(str, Enum):
    """베트맨 발매 대상 종목.

    `outcome_structure` 는 분석 단계에서 value 점수를 보정할 때 쓰입니다.
    축구처럼 무승부가 잦은 종목과 야구/농구처럼 사실상 2갈래인 종목을 구분합니다.
    """

    SOCCER = "soccer"
    BASEBALL = "baseball"
    BASKETBALL = "basketball"
    VOLLEYBALL = "volleyball"
    HOCKEY = "hockey"
    ESPORTS = "esports"

    @property
    def has_draw(self) -> bool:
        """정규 시간 무승부(승/무/패 3갈래)가 존재하는 종목인가."""
        return self in {Sport.SOCCER, Sport.HOCKEY}

    @property
    def is_core(self) -> bool:
        """출력 시 기본 섹션으로 보여줄 핵심 종목인가 (축구/야구/농구)."""
        return self in {Sport.SOCCER, Sport.BASEBALL, Sport.BASKETBALL}


class MarketType(str, Enum):
    """마켓(베팅 종류). 베트맨 프로토 승부식이 발매하는 마켓 전체."""

    MATCH_1X2 = "match_1x2"          # 승/무/패 (축구·하키)
    MONEYLINE = "moneyline"          # 승/패 2갈래 (야구·농구·배구)
    HANDICAP = "handicap"            # 핸디캡 (정수 라인: 승/무/패, .5 라인: 승/패)
    TOTALS = "totals"                # 언더/오버 (라인 기준)
    SUM = "sum"                      # 합산 홀/짝

    @property
    def needs_line(self) -> bool:
        """라인(기준점)이 의미를 갖는 마켓인가 (핸디캡·언오버)."""
        return self in {MarketType.HANDICAP, MarketType.TOTALS}


class Outcome(str, Enum):
    """마켓 내 선택지. 모든 마켓을 한 체계로 표현한다."""

    HOME = "home"          # 핸디캡에선 '핸디캡 적용 후 홈 승'
    DRAW = "draw"
    AWAY = "away"
    OVER = "over"
    UNDER = "under"
    ODD = "odd"            # SUM 홀
    EVEN = "even"          # SUM 짝


class MatchStatus(str, Enum):
    SCHEDULED = "scheduled"
    LIVE = "live"
    FINISHED = "finished"
    CANCELLED = "cancelled"


class SignalPolarity(str, Enum):
    """비정형 데이터(뉴스/분석글)에서 LLM이 추출한 신호의 방향."""

    POSITIVE = "positive"     # 해당 팀/선택지에 우호적
    NEGATIVE = "negative"     # 불리
    NEUTRAL = "neutral"
