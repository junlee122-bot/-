"""시장 신호: 라인 무브먼트 + CLV(클로징 라인 밸류).

프롬프트 요구:
  - 개장→종료 시간대별 라인 무브먼트를 기록해 시장 이동 추적.
  - 내가 베트맨에 베팅한 시점 배당과 Pinnacle 종료 배당을 비교해 CLV를 사후 기록.

CLV는 '내가 베팅한 가격이 종가(샤프 기준) 대비 얼마나 좋았는가'로, 장기적으로
샤프 시장을 이기는지 가늠하는 가장 신뢰받는 사후 지표다. 베트맨은 -EV 구조라도,
CLV가 꾸준히 양(+)이면 픽 선택 자체는 시장보다 앞섰다는 뜻이다.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..domain.enums import Outcome
from ..domain.features import LineMovement


@dataclass(frozen=True)
class MovementSignal:
    """한 선택지의 개장→현재 라인 이동 요약."""

    outcome: Outcome
    open_odds: float
    current_odds: float
    drift_pct: float          # (current-open)/open × 100. 음수=배당 짧아짐(쏠림)
    steaming: bool            # 배당이 의미있게 짧아짐(자금 유입)
    drifting: bool            # 배당이 의미있게 길어짐(자금 이탈)


def summarize_movements(
    movements: list[LineMovement], threshold_pct: float = 3.0
) -> list[MovementSignal]:
    out: list[MovementSignal] = []
    for m in movements:
        if m.open_odds <= 0:
            continue
        drift_pct = (m.current_odds - m.open_odds) / m.open_odds * 100.0
        out.append(
            MovementSignal(
                outcome=m.outcome,
                open_odds=m.open_odds,
                current_odds=m.current_odds,
                drift_pct=drift_pct,
                steaming=drift_pct <= -threshold_pct,
                drifting=drift_pct >= threshold_pct,
            )
        )
    return out


def implied_prob(decimal_odds: float) -> float:
    return 1.0 / decimal_odds if decimal_odds > 0 else 0.0


@dataclass(frozen=True)
class CLVResult:
    bet_odds: float            # 내가 베트맨에 베팅한 시점 배당
    closing_fair_prob: float   # Pinnacle 종료 de-vig 공정 확률
    clv_pct: float             # (bet_odds × closing_fair_prob − 1) × 100
    beat_closing: bool         # CLV > 0


def compute_clv(bet_odds: float, closing_fair_prob: float) -> CLVResult:
    """베팅 배당 × 종료 공정확률 − 1 = CLV.

    >0 이면 내가 잡은 가격이 종가(샤프 공정가)보다 유리했다는 뜻.
    """
    clv = bet_odds * closing_fair_prob - 1.0
    return CLVResult(
        bet_odds=bet_odds,
        closing_fair_prob=closing_fair_prob,
        clv_pct=clv * 100.0,
        beat_closing=clv > 0,
    )
