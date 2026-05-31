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
    """마켓(베팅 종류). 프로토 승부식은 1X2 / 머니라인이 중심."""

    MATCH_1X2 = "match_1x2"          # 승/무/패 (축구·하키)
    MONEYLINE = "moneyline"          # 승/패 2갈래 (야구·농구·배구)
    HANDICAP = "handicap"            # 핸디캡
    TOTALS = "totals"                # 오버/언더


class Outcome(str, Enum):
    """마켓 내 선택지. 1X2와 머니라인을 한 체계로 표현한다."""

    HOME = "home"
    DRAW = "draw"
    AWAY = "away"
    OVER = "over"
    UNDER = "under"


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
