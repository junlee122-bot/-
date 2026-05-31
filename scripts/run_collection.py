"""1단계 데모: mock 수집기로 데이터 수집 파이프라인을 실행한다.

종목별 예측 변수(feature) 수집·정규화와, 픽별 입력/결과 로깅까지 보여준다.

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
from betman.collection.mock.mock_features import MockFeatureCollector  # noqa: E402
from betman.collection.mock.mock_match import MockMatchCollector  # noqa: E402
from betman.collection.mock.mock_news import MockNewsCollector  # noqa: E402
from betman.collection.mock.mock_odds import MockOddsCollector  # noqa: E402
from betman.collection.pipeline import (  # noqa: E402
    DataCollectionPipeline,
    summarize_bundles,
)
from betman.domain.features import Feature, flatten_features  # noqa: E402
from betman.domain.models import CollectionRequest  # noqa: E402
from betman.analysis.provenance import JsonlPickLogger, build_snapshot  # noqa: E402
from betman.analysis.weights import weight_for  # noqa: E402


def _fmt(feat: Feature) -> str:
    return "결측" if not feat.present else str(feat.value)


def main() -> None:
    pipeline = DataCollectionPipeline(
        match_collector=MockMatchCollector(),
        odds_collector=MockOddsCollector(),
        betman_collector=MockBetmanCollector(),
        news_collector=MockNewsCollector(),
        feature_collector=MockFeatureCollector(),
    )

    request = CollectionRequest(
        sports=DEFAULT_CONFIG.sports,
        target_date=date(2026, 6, 1),
    )

    print("=" * 70)
    print("Betman Value Analyzer — 데이터 수집 데모 (mock)")
    print(f"환급률 전제: {DEFAULT_CONFIG.payout_rate:.0%}  "
          "→ 모든 항목의 장기 EV는 구조적으로 마이너스")
    print("=" * 70)

    bundles = pipeline.run(request)
    print(summarize_bundles(bundles))

    # 핵심 3종목에서 한 경기씩, 종목별 핵심 feature를 보여준다
    core = {}
    for b in bundles:
        s = b.match.sport
        if s in DEFAULT_CONFIG.core_sports and s not in core:
            core[s] = b

    for sport, b in core.items():
        f = b.features
        print("\n" + "-" * 70)
        print(f"[{sport.value}] {b.match.home.name} vs {b.match.away.name}"
              f"  ({b.match.league})")
        print("-" * 70)
        if sport.has_draw:
            print("  마켓: 승/무/패 3갈래 → 무 확률 별도 추정 대상")
        else:
            print("  마켓: 승/패 2갈래")

        # 종목 핵심 변수
        if sport.value == "soccer" and f.home.soccer:
            print(f"  [핵심] 홈 xG_for={_fmt(f.home.soccer.xg_for)} "
                  f"xGA={_fmt(f.home.soccer.xg_against)} | "
                  f"확정라인업={_fmt(f.home.soccer.confirmed_lineup)} "
                  f"결장={_fmt(f.home.soccer.key_absences)}")
            print(f"  무승부 경향={_fmt(f.soccer.draw_tendency)} "
                  f"리그득점환경={_fmt(f.soccer.league_scoring_env)}")
        elif sport.value == "baseball" and f.home.baseball:
            sp = f.home.baseball.starting_pitcher
            if sp.present:
                p = sp.value
                print(f"  [핵심] 홈 선발: {p.name}({p.throws}) "
                      f"ERA {p.era} FIP {p.fip} WHIP {p.whip}")
            else:
                print("  [핵심] 홈 선발: 결측(미발표)")
            print(f"  불펜피로={_fmt(f.home.baseball.bullpen_fatigue)} "
                  f"파크팩터={_fmt(f.baseball.park_factor)}")
        elif sport.value == "basketball" and f.home.basketball:
            print(f"  [핵심] 홈 백투백={_fmt(f.home.common.is_back_to_back)} "
                  f"휴식일={_fmt(f.home.common.rest_days)} "
                  f"스타결장={_fmt(f.home.basketball.star_absences)}")
            print(f"  공격효율={_fmt(f.home.basketball.offensive_rating)} "
                  f"페이스={_fmt(f.home.basketball.pace)}")

    # 픽별 입력/결과 로깅 데모 — 첫 경기의 모든 베트맨 선택지를 스냅샷
    if bundles:
        b = bundles[0]
        logger = JsonlPickLogger("data/pick_log.jsonl")
        n = 0
        for off in b.betman_offerings:
            snap = build_snapshot(
                pick_id=f"{b.match.id}:{off.outcome.value}",
                match_id=b.match.id,
                sport=b.match.sport,
                market=off.market,
                outcome=off.outcome,
                betman_odds=off.fixed_odds,
                match_features=b.features,
            )
            logger.log_pick(snap)
            n += 1
        print("\n" + "-" * 70)
        print(f"픽 입력 스냅샷 {n}건을 data/pick_log.jsonl 에 기록 "
              "(사후 검증용: feature 값 + 가중치 + 결측 여부)")

        # 가중치가 가장 큰 상위 feature 미리보기
        flat = flatten_features(b.features)
        ranked = sorted(
            ((n, weight_for(b.match.sport, n), feat)
             for n, feat in flat.items()),
            key=lambda t: t[1], reverse=True,
        )[:5]
        print("  이 경기에서 가중치 상위 입력:")
        for name, w, feat in ranked:
            print(f"    {name:<32} w={w:<4} {'(결측)' if not feat.present else ''}")


if __name__ == "__main__":
    main()
