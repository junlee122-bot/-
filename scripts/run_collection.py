"""1단계 데모: mock 수집기로 데이터 수집 파이프라인을 실행한다.

실행:
    python -m scripts.run_collection
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

# src 레이아웃을 import 경로에 추가
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from betman.config import DEFAULT_CONFIG  # noqa: E402
from betman.collection.mock.mock_betman import MockBetmanCollector  # noqa: E402
from betman.collection.mock.mock_match import MockMatchCollector  # noqa: E402
from betman.collection.mock.mock_news import MockNewsCollector  # noqa: E402
from betman.collection.mock.mock_odds import MockOddsCollector  # noqa: E402
from betman.collection.pipeline import (  # noqa: E402
    DataCollectionPipeline,
    summarize_bundles,
)
from betman.domain.models import CollectionRequest  # noqa: E402


def main() -> None:
    pipeline = DataCollectionPipeline(
        match_collector=MockMatchCollector(),
        odds_collector=MockOddsCollector(),
        betman_collector=MockBetmanCollector(),
        news_collector=MockNewsCollector(),
    )

    request = CollectionRequest(
        sports=DEFAULT_CONFIG.sports,
        target_date=date(2026, 6, 1),
    )

    print("=" * 64)
    print("Betman Value Analyzer — 1단계 데이터 수집 데모 (mock)")
    print(f"환급률 전제: {DEFAULT_CONFIG.payout_rate:.0%}  "
          "→ 모든 항목의 장기 EV는 구조적으로 마이너스")
    print("=" * 64)

    bundles = pipeline.run(request)
    print(summarize_bundles(bundles))

    # 한 경기 상세: 해외 배당 vs 베트맨 배당을 나란히 (de-vig/EV는 3단계에서)
    if bundles:
        b = bundles[0]
        print("\n" + "-" * 64)
        print(f"상세 예시: {b.match.home.name} vs {b.match.away.name}")
        print("-" * 64)
        print("베트맨 고정배당:")
        for o in b.betman_offerings:
            print(f"  {o.outcome.value:<6} {o.fixed_odds:>6.2f}  (회차 {o.round_no})")
        print("해외 컨센서스 입력(북메이커별, 참고용):")
        seen = set()
        for q in b.overseas_odds:
            if q.bookmaker in seen:
                continue
            seen.add(q.bookmaker)
            same = [x for x in b.overseas_odds if x.bookmaker == q.bookmaker]
            odds_str = "  ".join(f"{x.outcome.value}:{x.decimal_odds:.2f}" for x in same)
            print(f"  {q.bookmaker:<18} {odds_str}")
        if b.news:
            print("비정형 신호 원문(3단계 LLM 입력 대기):")
            for n in b.news[:3]:
                print(f"  · [{n.source}] {n.title}")


if __name__ == "__main__":
    main()
