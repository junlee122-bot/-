"""3단계 데모: 수집 → 분석 → 픽 줄세우기 + 로깅.

Pinnacle 샤프 기준선 de-vig 공정확률, edge(%), EV(환급률 63%), value 점수,
평균회귀/라인무브먼트/비정형 신호, CLV(가상) 까지 보여준다.

실행:
    python -m scripts.run_analysis
"""

from __future__ import annotations

import sys
from dataclasses import asdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from betman.config import DEFAULT_CONFIG  # noqa: E402
from betman.collection.mock.mock_betman import MockBetmanCollector  # noqa: E402
from betman.collection.mock.mock_features import MockFeatureCollector  # noqa: E402
from betman.collection.mock.mock_match import MockMatchCollector  # noqa: E402
from betman.collection.mock.mock_news import MockNewsCollector  # noqa: E402
from betman.collection.mock.mock_odds import MockOddsCollector  # noqa: E402
from betman.collection.pipeline import DataCollectionPipeline  # noqa: E402
from betman.domain.enums import Sport  # noqa: E402
from betman.domain.models import CollectionRequest  # noqa: E402
from betman.analysis.value import (  # noqa: E402
    DefaultValueAnalyzer,
    analyze_bundles,
    payout_note,
)
from betman.analysis.market import compute_clv  # noqa: E402
from betman.analysis.provenance import (  # noqa: E402
    JsonlPickLogger,
    snapshot_from_pick,
)


def main() -> None:
    pipeline = DataCollectionPipeline(
        MockMatchCollector(),
        MockOddsCollector(),
        MockBetmanCollector(),
        MockNewsCollector(),
        MockFeatureCollector(),
    )
    bundles = pipeline.run(
        CollectionRequest(sports=DEFAULT_CONFIG.sports, target_date=date(2026, 6, 1))
    )
    bundle_by_id = {b.match.id: b for b in bundles}

    analyzer = DefaultValueAnalyzer()
    picks = analyze_bundles(bundles, analyzer)

    print("=" * 78)
    print("Betman Value Analyzer — 3단계 분석 데모 (mock)")
    print(payout_note())
    print("=" * 78)

    # 핵심 3종목 섹션: value 점수 순
    for sport in DEFAULT_CONFIG.core_sports:
        sp_picks = [
            p for p in picks if bundle_by_id[p.match_id].match.sport == sport
        ]
        if not sp_picks:
            continue
        print(f"\n### {sport.value.upper()} (value 점수 순) ###")
        print(f"{'경기':<22}{'선택':<6}{'배당':>6}{'공정%':>7}"
              f"{'edge%':>8}{'EV':>8}{'value':>8}  근거")
        for p in sp_picks[:6]:
            m = bundle_by_id[p.match_id].match
            label = f"{m.home.name} vs {m.away.name}"[:20]
            sig = ""
            if p.supporting_signals:
                sig = f"신호{len(p.supporting_signals)} "
            mr = "평균회귀 " if p.mean_reversion else ""
            note = sig + mr + (p.notes[1] if len(p.notes) > 1 else p.notes[0])
            print(f"{label:<22}{p.outcome.value:<6}{p.betman_odds:>6.2f}"
                  f"{p.fair_prob*100:>7.1f}{p.edge_pct:>8.1f}"
                  f"{p.expected_value:>8.2f}{p.value_score:>8.2f}  {note}")

    # '주목 픽': 비핵심 종목 중 종목별 기준선 넘는 것만
    from betman.analysis.value import calibration_for

    notable = []
    for p in picks:
        sp = bundle_by_id[p.match_id].match.sport
        if sp in DEFAULT_CONFIG.core_sports:
            continue
        if p.value_score >= calibration_for(sp).notable_threshold:
            notable.append((sp, p))
    if notable:
        print("\n### 주목 픽 (비핵심 종목, 기준선 통과) ###")
        for sp, p in sorted(notable, key=lambda t: t[1].value_score, reverse=True)[:8]:
            m = bundle_by_id[p.match_id].match
            print(f"  [{sp.value}] {m.home.name} vs {m.away.name} "
                  f"{p.outcome.value} 배당{p.betman_odds:.2f} "
                  f"edge{p.edge_pct:+.1f}% value{p.value_score:.2f}")

    # 픽별 입력/분석/결과 로깅 (사후 검증) + CLV(가상) 데모
    logger = JsonlPickLogger("data/analysis_log.jsonl")
    logged = 0
    for p in picks:
        b = bundle_by_id[p.match_id]
        if b.features is None:
            continue
        snap = snapshot_from_pick(p, b.features)
        logger.log_pick(snap)
        logged += 1
    print("\n" + "-" * 78)
    print(f"픽 {logged}건을 data/analysis_log.jsonl 에 기록 "
          "(입력 feature + 가중치 + 공정확률 + edge + EV + value)")

    # CLV 데모: 베팅 배당과 (가상) Pinnacle 종료 공정확률 비교
    if picks:
        p = picks[0]
        # 가상의 종료 공정확률 = 분석 시 공정확률에 소폭 변화를 준 값
        closing_fair = min(0.99, p.fair_prob * 1.02)
        clv = compute_clv(p.betman_odds, closing_fair)
        logger.log_clv(f"{p.match_id}:{p.outcome.value}", clv.clv_pct, clv.beat_closing)
        print(f"CLV 예시: {p.match_id} {p.outcome.value} "
              f"베팅배당 {p.betman_odds:.2f} vs 종료공정 {closing_fair:.3f} "
              f"→ CLV {clv.clv_pct:+.1f}% "
              f"({'종가 이김' if clv.beat_closing else '종가에 밀림'})")

    print("\n주의: 위 EV는 대부분 음수입니다. 이 도구는 베팅을 권유하지 않으며, "
          "'덜 불리한' 항목을 비교·줄세우기 위한 분석 보조입니다.")


if __name__ == "__main__":
    main()
