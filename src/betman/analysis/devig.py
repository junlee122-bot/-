"""배당 → 공정 확률 변환 (de-vig).

핵심 전제(프롬프트): Pinnacle 배당을 '샤프 기준선'으로 삼아 마진을 제거한
공정 확률을 '진짜 확률'의 기준으로 사용한다. Pinnacle 호가가 없으면 가용한
여러 북메이커 컨센서스로 폴백한다.

de-vig 방식:
  - proportional: p_i = (1/o_i) / Σ(1/o_j)  — 가장 단순/표준
  - power(멱승법): 각 내재확률을 지수 k로 보정해 합이 1이 되도록 — 즐겨찾기
    -긴꼬리 편향(favorite-longshot bias)을 일부 완화. 기본은 proportional.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..domain.enums import Outcome
from ..domain.models import OddsQuote
from .base import DevigStrategy

# Pinnacle 식별자 (mock/실데이터 공통 접두 매칭)
PINNACLE_KEYS = ("pinnacle", "pinnacle_mock")


class ProportionalDevig(DevigStrategy):
    """비례 정규화: 내재확률을 합이 1이 되도록 나눈다."""

    def devig(self, implied_probs: dict[Outcome, float]) -> dict[Outcome, float]:
        total = sum(implied_probs.values())
        if total <= 0:
            return {k: 0.0 for k in implied_probs}
        return {k: v / total for k, v in implied_probs.items()}


class PowerDevig(DevigStrategy):
    """멱승법: p_i ∝ (1/o_i)^k, Σp_i = 1 이 되도록 k를 이분 탐색.

    k>1 이면 favorite 확률을 키우고 longshot을 줄인다. 단순 비례보다 시장
    편향을 더 잘 반영한다는 연구가 있어 옵션으로 제공.
    """

    def __init__(self, iterations: int = 60) -> None:
        self._iters = iterations

    def devig(self, implied_probs: dict[Outcome, float]) -> dict[Outcome, float]:
        items = [(k, v) for k, v in implied_probs.items() if v > 0]
        if not items:
            return {k: 0.0 for k in implied_probs}

        def total_for(k: float) -> float:
            return sum(v ** k for _, v in items)

        lo, hi = 0.5, 5.0
        for _ in range(self._iters):
            mid = (lo + hi) / 2
            if total_for(mid) > 1.0:
                lo = mid
            else:
                hi = mid
        k = (lo + hi) / 2
        s = total_for(k) or 1.0
        out = {key: (v ** k) / s for key, v in items}
        for key in implied_probs:
            out.setdefault(key, 0.0)
        return out


@dataclass(frozen=True)
class FairLine:
    """한 경기에 대한 공정 확률 추정 결과."""

    fair_probs: dict[Outcome, float]        # Pinnacle 기준(없으면 컨센서스)
    consensus_probs: dict[Outcome, float]   # 전체 북메이커 컨센서스
    source: str                             # "pinnacle" | "consensus" | "none"
    bookmaker_count: int
    overround: float                        # Pinnacle 마진(있을 때), 없으면 컨센서스


def _implied_by_outcome(quotes: list[OddsQuote]) -> dict[Outcome, float]:
    """같은 북메이커 묶음의 선택지별 내재확률(1/배당). 중복은 최신만."""
    out: dict[Outcome, float] = {}
    for q in quotes:
        if q.decimal_odds > 0:
            out[q.outcome] = 1.0 / q.decimal_odds
    return out


def _is_pinnacle(name: str) -> bool:
    n = name.lower()
    return any(n.startswith(k) or n == k for k in PINNACLE_KEYS)


def compute_fair_line(
    overseas_odds: list[OddsQuote],
    strategy: DevigStrategy | None = None,
) -> FairLine:
    """해외 배당에서 공정 확률을 계산한다.

    1) Pinnacle 호가가 있으면 그것만 de-vig → fair_probs (샤프 기준선).
    2) 모든 북메이커의 선택지별 평균 내재확률을 de-vig → consensus_probs.
    3) Pinnacle 없으면 fair_probs = consensus_probs.
    """
    strategy = strategy or ProportionalDevig()
    books: dict[str, list[OddsQuote]] = {}
    for q in overseas_odds:
        books.setdefault(q.bookmaker, []).append(q)

    # 컨센서스: 선택지별 북메이커 평균 내재확률
    sum_implied: dict[Outcome, float] = {}
    cnt_implied: dict[Outcome, int] = {}
    for quotes in books.values():
        for oc, ip in _implied_by_outcome(quotes).items():
            sum_implied[oc] = sum_implied.get(oc, 0.0) + ip
            cnt_implied[oc] = cnt_implied.get(oc, 0) + 1
    avg_implied = {
        oc: sum_implied[oc] / cnt_implied[oc] for oc in sum_implied
    }
    consensus = strategy.devig(avg_implied) if avg_implied else {}
    consensus_overround = sum(avg_implied.values()) - 1.0 if avg_implied else 0.0

    # Pinnacle 기준선
    pin_name = next((b for b in books if _is_pinnacle(b)), None)
    if pin_name:
        pin_implied = _implied_by_outcome(books[pin_name])
        fair = strategy.devig(pin_implied)
        return FairLine(
            fair_probs=fair,
            consensus_probs=consensus,
            source="pinnacle",
            bookmaker_count=len(books),
            overround=sum(pin_implied.values()) - 1.0,
        )

    if consensus:
        return FairLine(
            fair_probs=consensus,
            consensus_probs=consensus,
            source="consensus",
            bookmaker_count=len(books),
            overround=consensus_overround,
        )

    return FairLine({}, {}, "none", 0, 0.0)
