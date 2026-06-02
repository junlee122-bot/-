"""전체 파이프라인: 수집 → 분석 → Supabase 적재.

대시보드(Next.js)가 읽을 picks 테이블과 pick_logs(사후 검증)를 채운다.

사전: schema.sql 을 Supabase SQL Editor 에서 1회 실행, .env 설정.
실행:
    python -m scripts.run_full_pipeline
"""

from __future__ import annotations

import os
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

    # 2) 분석 → picks 먼저 적재 (대시보드가 읽는 건 picks 뿐 → 최우선)
    analyzer = DefaultValueAnalyzer()
    pick_rows, snapshots = [], []
    for b in bundles:
        for p in analyzer.analyze(b):
            pick_rows.append(pick_to_row(p, b))
            if b.features is not None:
                snapshots.append(asdict(snapshot_from_pick(p, b.features)))
    repo.replace_all_picks(pick_rows)
    print(f"• 분석 픽 {len(pick_rows)}건 → picks 적재 OK (기존 교체)")

    # 3) 사후검증 로그 (picks 다음 우선순위)
    for snap in snapshots:
        repo.save_pick_snapshot(snap)
    print(f"• 픽 로그 {len(snapshots)}건 → pick_logs 적재 OK")

    # 4) 원시 데이터(경기/배당) 적재 — 무겁고 대시보드에 불필요.
    #    SAVE_RAW=1 일 때만. (Firestore REST 는 문서당 1요청이라 느림)
    if os.environ.get("SAVE_RAW") == "1":
        try:
            repo.save_bundles(bundles)
            print("• 원시 경기/배당 적재 OK (SAVE_RAW=1)")
        except Exception as e:
            print(f"  (원시 적재 일부 실패: {str(e)[:80]})")
    else:
        print("• 원시 경기/배당 적재 건너뜀 (SAVE_RAW=1 로 활성화)")

    repo.close()
    print("\n✓ 완료. 대시보드에 picks 가 표시됩니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
