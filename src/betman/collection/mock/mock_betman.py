"""mock BetmanCollector — 베트맨 발매 항목 + 고정배당 생성.

베트맨 고정배당은 해외 컨센서스보다 환급률(63%)만큼 더 짠 배당을 주는 경향을
모사한다. 일부 경기는 미발매(빈 리스트)로 만들어 파이프라인의 필터링을 테스트한다.
"""

from __future__ import annotations

import random

from ...config import BETMAN_PAYOUT_RATE
from ...domain.enums import MarketType, Outcome
from ...domain.models import BetmanOffering, Match
from ..base import BetmanCollector
from ._fixtures import seed_from
from .mock_odds import _true_probs


class MockBetmanCollector(BetmanCollector):
    def collect_offerings(self, match: Match) -> list[BetmanOffering]:
        rng = random.Random(seed_from(match.id, "betman"))

        # 약 20% 경기는 베트맨 미발매로 처리
        if rng.random() < 0.2:
            return []

        market = (
            MarketType.MATCH_1X2 if match.sport.has_draw else MarketType.MONEYLINE
        )
        true_p = _true_probs(
            random.Random(seed_from(match.id, "odds-true")), match.sport.has_draw
        )
        round_no = f"{match.start_time:%y}{rng.randint(1, 60):02d}"

        offerings: list[BetmanOffering] = []
        for outcome, p in true_p.items():
            # 베트맨 고정배당 = (1/확률) × 환급률 × 항목별 작은 변동
            # → 평균적으로 해외 공정배당보다 약 63% 수준으로 낮음
            jitter = rng.uniform(0.97, 1.05)
            fixed = round((1.0 / p) * BETMAN_PAYOUT_RATE * jitter, 2)
            offerings.append(
                BetmanOffering(
                    match_id=match.id,
                    round_no=round_no,
                    market=market,
                    outcome=outcome,
                    fixed_odds=max(1.01, fixed),
                    sales_open=True,
                )
            )
        return offerings
