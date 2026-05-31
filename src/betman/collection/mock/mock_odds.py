"""mock OddsCollector — 여러 해외 북메이커의 배당 생성.

내부적으로 '진짜 확률'을 하나 정한 뒤, 북메이커마다 약간의 마진을 얹고
잡음을 더해 십진 배당으로 변환한다. (분석 레이어의 de-vig 테스트에 적합)
"""

from __future__ import annotations

import random

from ...domain.enums import MarketType, Outcome
from ...domain.models import Match, OddsQuote
from ..base import OddsCollector
from ._fixtures import seed_from

# 해외 북메이커(가상) — 참고용. 실제 베팅 대상 아님.
_BOOKMAKERS = ["pinnacle_mock", "bet365_mock", "williamhill_mock", "marathon_mock"]


def _true_probs(rng: random.Random, has_draw: bool) -> dict[Outcome, float]:
    """정규화된 '진짜' 확률(마진 없음)."""
    if has_draw:
        raw = {
            Outcome.HOME: rng.uniform(0.30, 0.55),
            Outcome.DRAW: rng.uniform(0.20, 0.32),
            Outcome.AWAY: rng.uniform(0.25, 0.45),
        }
    else:
        raw = {
            Outcome.HOME: rng.uniform(0.40, 0.62),
            Outcome.AWAY: rng.uniform(0.38, 0.60),
        }
    total = sum(raw.values())
    return {k: v / total for k, v in raw.items()}


class MockOddsCollector(OddsCollector):
    def collect_odds(self, match: Match) -> list[OddsQuote]:
        market = (
            MarketType.MATCH_1X2 if match.sport.has_draw else MarketType.MONEYLINE
        )
        base_rng = random.Random(seed_from(match.id, "odds-true"))
        true_p = _true_probs(base_rng, match.sport.has_draw)

        quotes: list[OddsQuote] = []
        for book in _BOOKMAKERS:
            rng = random.Random(seed_from(match.id, book))
            # 북메이커 마진 4~8% (오버라운드)
            margin = rng.uniform(0.04, 0.08)
            for outcome, p in true_p.items():
                # 진짜 확률에 약간의 북메이커별 잡음 + 마진 반영
                noisy = max(0.01, p * rng.uniform(0.95, 1.05))
                priced_p = noisy * (1 + margin)
                decimal = round(1.0 / priced_p, 2)
                quotes.append(
                    OddsQuote(
                        bookmaker=book,
                        market=market,
                        outcome=outcome,
                        decimal_odds=decimal,
                        captured_at=match.start_time,
                    )
                )
        return quotes
