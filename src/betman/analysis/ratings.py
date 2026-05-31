"""팀 강도 레이팅 (종목별 Elo).

프롬프트 요구: "팀 강도 추정에 Elo 또는 그에 준하는 레이팅을 종목별로 운영."

종목마다 홈 어드밴티지/K-팩터/무승부 처리(축구)가 다르므로 파라미터를 종목별로
둔다. 레이팅은 과거 결과로 업데이트하며(저장 레이어의 경기 결과 사용), 경기
예측 시 두 팀 레이팅 차이를 승/무/패 확률로 변환한다.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from ..domain.enums import Outcome, Sport


@dataclass(frozen=True)
class EloParams:
    k: float                 # 업데이트 강도
    home_adv: float          # 홈 어드밴티지(레이팅 점수)
    draw_base: float = 0.0   # 무승부 기본 경향(축구 등 3갈래에서만)
    scale: float = 400.0     # 로지스틱 스케일


# 종목별 사전 파라미터 (백테스트로 재캘리브레이션 대상)
_PARAMS: dict[Sport, EloParams] = {
    Sport.SOCCER: EloParams(k=20, home_adv=60, draw_base=0.26),
    Sport.BASEBALL: EloParams(k=8, home_adv=24),     # 야구는 변동성↑ → K 낮게
    Sport.BASKETBALL: EloParams(k=20, home_adv=100), # 홈코트 강함
    Sport.VOLLEYBALL: EloParams(k=18, home_adv=50),
    Sport.HOCKEY: EloParams(k=16, home_adv=50, draw_base=0.20),
    Sport.ESPORTS: EloParams(k=24, home_adv=0),
}

DEFAULT_RATING = 1500.0


def params_for(sport: Sport) -> EloParams:
    return _PARAMS.get(sport, EloParams(k=20, home_adv=40))


def expected_score(rating_a: float, rating_b: float, scale: float = 400.0) -> float:
    """A가 B를 상대로 한 기대 승률(0~1)."""
    return 1.0 / (1.0 + 10 ** ((rating_b - rating_a) / scale))


def win_draw_loss_probs(
    home_rating: float, away_rating: float, sport: Sport
) -> dict[Outcome, float]:
    """레이팅 차이를 승/무/패 확률로 변환.

    2갈래 종목(야구·농구)은 무승부 없이 home/away만. 3갈래(축구·하키)는
    기대 승률에서 무승부 몫을 떼 분배(단순 모델, value 보정용 보조 신호).
    """
    p = params_for(sport)
    eh = expected_score(home_rating + p.home_adv, away_rating, p.scale)

    if not sport.has_draw:
        return {Outcome.HOME: eh, Outcome.AWAY: 1.0 - eh}

    # 3갈래: 무승부 확률은 두 팀이 비슷할수록 커지도록 draw_base를 조정
    closeness = 1.0 - abs(eh - 0.5) * 2          # 0(불균형)~1(균형)
    p_draw = max(0.05, min(0.40, p.draw_base * (0.6 + 0.8 * closeness)))
    p_home = eh * (1.0 - p_draw)
    p_away = (1.0 - eh) * (1.0 - p_draw)
    total = p_home + p_draw + p_away
    return {
        Outcome.HOME: p_home / total,
        Outcome.DRAW: p_draw / total,
        Outcome.AWAY: p_away / total,
    }


def update_ratings(
    home_rating: float,
    away_rating: float,
    home_result: float,    # 1.0 승 / 0.5 무 / 0.0 패 (홈 기준)
    sport: Sport,
) -> tuple[float, float]:
    """경기 결과로 두 팀 레이팅을 갱신해 반환."""
    p = params_for(sport)
    eh = expected_score(home_rating + p.home_adv, away_rating, p.scale)
    delta = p.k * (home_result - eh)
    return home_rating + delta, away_rating - delta


class EloBook:
    """팀별 레이팅 저장소(메모리). 저장 레이어와 연동해 영속화 가능."""

    def __init__(self) -> None:
        self._ratings: dict[str, float] = {}

    def get(self, team_id: str) -> float:
        return self._ratings.get(team_id, DEFAULT_RATING)

    def set(self, team_id: str, rating: float) -> None:
        self._ratings[team_id] = rating

    def record_result(
        self, home_id: str, away_id: str, home_result: float, sport: Sport
    ) -> None:
        hr, ar = update_ratings(
            self.get(home_id), self.get(away_id), home_result, sport
        )
        self.set(home_id, hr)
        self.set(away_id, ar)
