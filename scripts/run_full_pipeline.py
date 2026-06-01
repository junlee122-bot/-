"""전체 파이프라인: 수집 → 분석 → Supabase 적재.

대시보드(Next.js)가 읽을 picks 테이블과 pick_logs(사후 검증)를 채운다.

사전: schema.sql 을 Supabase SQL Editor 에서 1회 실행, .env 설정.
실행:
    python -m scripts.run_full_pipeline
"""

from __future__ import annotations

import sys
from dataclasses import asdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from betman.config import load_app_config, load_firebase_settings  # noqa: E402
from betman.collection.sources import build_collectors  # noqa: E402
from betman.collection.pipeline import DataCollectionPipeline  # noqa: E402
from betman.domain.models import CollectionRequest  # noqa: E402
from betman.analysis.value import DefaultValueAnalyzer  # noqa: E402
from betman.analysis.provenance import snapshot_from_pick  # noqa: E402


def pick_to_row(pick, bundle) -> dict:
    """PickAnalysis → picks 테이블 행 (대시보드 표시용 비정규화 포함)."""
    m = bundle.match
    return {
        # 마켓·라인까지 포함해 고유 키 생성(1X2 home 과 핸디캡 home 충돌 방지)
        "pick_id": (
            f"{pick.match_id}:{pick.market.value}"
            f":{pick.line if pick.line is not None else ''}:{pick.outcome.value}"
        ),
        "match_id": pick.match_id,
        "sport": m.sport.value,
        "league": m.league,
        "home_name": m.home.name,
        "away_name": m.away.name,
        "start_time": m.start_time.isoformat(),
        "market": pick.market.value,
        "outcome": pick.outcome.value,
        "betman_odds": pick.betman_odds,
        "fair_prob": pick.fair_prob,
        "consensus_prob": pick.consensus_prob,
        "betman_implied_prob": pick.betman_implied_prob,
        "edge_pct": pick.edge_pct,
        "expected_value": pick.expected_value,
        "value_score": pick.value_score,
        "mean_reversion": pick.mean_reversion,
        "line": pick.line,
        "model_based": pick.model_based,
        "is_core": m.sport.is_core,
        "notes": list(pick.notes),
        "signals": [
            {
                "polarity": s.polarity.value,
                "confidence": s.confidence,
                "summary": s.summary,
            }
            for s in pick.supporting_signals
        ],
    }


def main() -> int:
    settings = load_firebase_settings()
    if not settings.configured:
        print("✗ Firebase 미설정. .env 에 서비스계정 자격을 설정하세요.")
        return 1

    try:
        from betman.storage.firestore_repo import FirestoreMatchRepository
        repo = FirestoreMatchRepository(settings)
    except Exception as e:
        print(f"✗ 저장소 초기화 실패: {e}")
        return 1

    # 1) 수집 (mock/live 는 DATA_SOURCE_MODE 로 선택)
    config = load_app_config()
    cs = build_collectors(config)
    print(f"• 데이터 소스 모드: {config.data_source_mode}")
    for n in cs.notes:
        print(f"    - {n}")
    pipeline = DataCollectionPipeline(
        cs.match, cs.odds, cs.betman, cs.news, cs.features,
    )
    # live: 실제 발매일(오늘) 기준, mock: 데모 고정일
    target = date.today() if config.data_source_mode == "live" else date(2026, 6, 1)
    bundles = pipeline.run(
        CollectionRequest(sports=config.sports, target_date=target)
    )
    print(f"• 수집: {len(bundles)}경기")

    # 2) 저장(경기/배당/팀)
    try:
        repo.save_bundles(bundles)
        print("• 경기/배당 적재 OK")
    except Exception as e:
        print(f"✗ 적재 실패: {e}")
        repo.close()
        return 1

    # 3) 분석 → picks + pick_logs 적재
    analyzer = DefaultValueAnalyzer()
    bundle_by_id = {b.match.id: b for b in bundles}
    pick_rows, log_count = [], 0
    for b in bundles:
        for p in analyzer.analyze(b):
            pick_rows.append(pick_to_row(p, b))
            if b.features is not None:
                repo.save_pick_snapshot(asdict(snapshot_from_pick(p, b.features)))
                log_count += 1
    # 기존 picks 비우고 새로 적재(대시보드는 최신 분석만 표시)
    repo.replace_all_picks(pick_rows)
    print(f"• 분석 픽 {len(pick_rows)}건 → picks 적재 OK (기존 교체)")
    print(f"• 픽 로그 {log_count}건 → pick_logs 적재 OK (사후 검증)")

    repo.close()
    print("\n✓ 전체 파이프라인 완료. 대시보드에서 picks 를 표시할 수 있습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
