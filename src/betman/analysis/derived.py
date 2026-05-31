"""파생 마켓 공정확률 엔진 (포아송 모델).

Pinnacle 1X2 de-vig 공정확률(=진짜 확률 기준)에서 양 팀 기대득점 λ_home, λ_away
를 역산하고, 이를 이용해 베트맨이 발매하는 파생 마켓의 공정확률을 추가 API 호출
없이 계산한다.

- 핸디캡(정수): 홈 점수에 핸디캡을 더한 뒤 승/무/패
- 핸디캡(.5): 무승부 없이 승/패
- 언더오버: 총득점이 라인 미만/초과
- SUM 홀짝: 총득점의 홀짝

축구·하키처럼 득점이 비교적 낮고 독립적인 종목에서 포아송 근사가 잘 맞는다.
야구/농구처럼 득점 분포가 다른 종목은 핸디캡/언오버 해석이 달라 여기서는
축구·하키(3갈래) 위주로 적용하고, 그 외 종목은 호출측에서 제외한다.

핵심 한계(정직성): 이것은 '모델 추정 공정확률'이다. Pinnacle이 직접 제시한
1X2 만큼의 신뢰도는 아니며, 라인이 멀어질수록(예: 소수핸디캡) 오차가 커진다.
분석 결과에 model_based=True 로 표시해 신뢰도를 낮춘다.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from ..domain.enums import Outcome

# 포아송 합산 상한 (각 팀 득점 0..MAX_GOALS)
_MAX_GOALS = 15


@dataclass(frozen=True)
class GoalModel:
    """양 팀 기대득점."""

    lam_home: float
    lam_away: float


def _pois_pmf(k: int, lam: float) -> float:
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return math.exp(-lam) * lam**k / math.factorial(k)


def _score_grid(model: GoalModel) -> list[list[float]]:
    """P(home=i, away=j) 격자 (독립 포아송)."""
    ph = [_pois_pmf(i, model.lam_home) for i in range(_MAX_GOALS + 1)]
    pa = [_pois_pmf(j, model.lam_away) for j in range(_MAX_GOALS + 1)]
    return [[ph[i] * pa[j] for j in range(_MAX_GOALS + 1)] for i in range(_MAX_GOALS + 1)]


def infer_goal_model(
    p_home: float, p_draw: float, p_away: float, total_hint: float = 2.6
) -> GoalModel | None:
    """1X2 공정확률 → (lam_home, lam_away) 역산.

    2개 자유도(λ_home, λ_away)를 두 목표(P(home승), P(away승))에 맞춘다.
    P(draw)는 종속적으로 따라온다. 총득점 평균은 total_hint 근방에서 시작해
    좌표하강법으로 맞춘다. 해를 못 찾으면 None.
    """
    if p_home <= 0 or p_away <= 0 or p_home + p_draw + p_away <= 0:
        return None
    # 정규화
    s = p_home + p_draw + p_away
    p_home, p_draw, p_away = p_home / s, p_draw / s, p_away / s

    # 초기값: 총득점 total_hint 를 승률 비로 배분
    strength = p_home / (p_home + p_away)
    lam_h = total_hint * (0.4 + 0.4 * strength)
    lam_a = total_hint - lam_h
    lam_h, lam_a = max(0.1, lam_h), max(0.1, lam_a)

    def probs(lh: float, la: float) -> tuple[float, float, float]:
        ph = [_pois_pmf(i, lh) for i in range(_MAX_GOALS + 1)]
        pa = [_pois_pmf(j, la) for j in range(_MAX_GOALS + 1)]
        home = draw = away = 0.0
        for i in range(_MAX_GOALS + 1):
            for j in range(_MAX_GOALS + 1):
                p = ph[i] * pa[j]
                if i > j:
                    home += p
                elif i == j:
                    draw += p
                else:
                    away += p
        return home, draw, away

    # 좌표하강: λ_home, λ_away 를 번갈아 조정해 (home, away) 오차 최소화
    for _ in range(200):
        h, d, a = probs(lam_h, lam_a)
        err_h, err_a = p_home - h, p_away - a
        if abs(err_h) < 1e-4 and abs(err_a) < 1e-4:
            break
        # 득점 늘리면 그 팀 승률↑. 비례 보정.
        lam_h = max(0.05, min(6.0, lam_h * (1 + 0.8 * err_h)))
        lam_a = max(0.05, min(6.0, lam_a * (1 + 0.8 * err_a)))

    return GoalModel(lam_h, lam_a)


# --------------------------------------------------------------------------- #
# 파생 마켓 공정확률
# --------------------------------------------------------------------------- #
def handicap_probs(model: GoalModel, line: float) -> dict[Outcome, float]:
    """핸디캡(홈 기준 line). 정수면 승/무/패, .5면 승/패.

    예: line=-1.0 → 홈 점수에 -1 적용 후 (home-1) vs away 비교.
    """
    grid = _score_grid(model)
    home = draw = away = 0.0
    is_half = abs(line - round(line)) > 1e-9
    for i in range(_MAX_GOALS + 1):
        for j in range(_MAX_GOALS + 1):
            p = grid[i][j]
            adj = (i + line) - j
            if adj > 0:
                home += p
            elif adj < 0:
                away += p
            else:
                draw += p
    if is_half:
        # 무승부 없음
        return {Outcome.HOME: home, Outcome.AWAY: away}
    return {Outcome.HOME: home, Outcome.DRAW: draw, Outcome.AWAY: away}


def totals_probs(model: GoalModel, line: float) -> dict[Outcome, float]:
    """언더/오버. 총득점이 line 미만=under, 초과=over (정확히 같으면 푸시→제외)."""
    grid = _score_grid(model)
    under = over = 0.0
    for i in range(_MAX_GOALS + 1):
        for j in range(_MAX_GOALS + 1):
            total = i + j
            p = grid[i][j]
            if total < line:
                under += p
            elif total > line:
                over += p
            # total == line (정수 라인 푸시) 는 제외
    s = under + over
    if s <= 0:
        return {}
    return {Outcome.UNDER: under / s, Outcome.OVER: over / s}


def sum_oddeven_probs(model: GoalModel) -> dict[Outcome, float]:
    """총득점 홀/짝 확률."""
    grid = _score_grid(model)
    odd = even = 0.0
    for i in range(_MAX_GOALS + 1):
        for j in range(_MAX_GOALS + 1):
            p = grid[i][j]
            if (i + j) % 2 == 0:
                even += p
            else:
                odd += p
    return {Outcome.ODD: odd, Outcome.EVEN: even}
