"""Supabase 저장 레이어 점검/스모크 테스트.

사전 준비(1회): Supabase 대시보드 → SQL Editor 에서 schema.sql 실행.
그 다음 .env 에 SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY 설정 후:

    python -m scripts.init_supabase

수행: 연결 확인 → mock 경기 수집 → 저장 → 팀 전적 upsert/조회 →
픽 스냅샷 저장/조회. (네트워크가 열린 환경에서 실행할 것)
"""

from __future__ import annotations

import sys
from dataclasses import asdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from betman.config import DEFAULT_CONFIG, load_supabase_settings  # noqa: E402
from betman.collection.mock.mock_betman import MockBetmanCollector  # noqa: E402
from betman.collection.mock.mock_features import MockFeatureCollector  # noqa: E402
from betman.collection.mock.mock_match import MockMatchCollector  # noqa: E402
from betman.collection.mock.mock_news import MockNewsCollector  # noqa: E402
from betman.collection.mock.mock_odds import MockOddsCollector  # noqa: E402
from betman.collection.pipeline import DataCollectionPipeline  # noqa: E402
from betman.domain.enums import Sport  # noqa: E402
from betman.domain.models import CollectionRequest, TeamRecord  # noqa: E402
from betman.analysis.provenance import build_snapshot  # noqa: E402


def main() -> int:
    settings = load_supabase_settings()
    if not settings.configured:
        print("✗ Supabase 미설정. .env 에 다음을 넣어주세요:")
        print("    SUPABASE_URL=https://<ref>.supabase.co")
        print("    SUPABASE_SERVICE_ROLE_KEY=<service_role_jwt>")
        return 1

    masked = (settings.write_key or "")[:8] + "…"
    print(f"• Supabase URL : {settings.url}")
    print(f"• 사용 키      : service_role={bool(settings.service_role_key)} "
          f"(앞 8자리 {masked})")

    try:
        from betman.storage.supabase_repo import SupabaseMatchRepository
    except Exception as e:  # pragma: no cover
        print(f"✗ httpx 필요: pip install httpx  ({e})")
        return 1

    try:
        repo = SupabaseMatchRepository(settings)
    except RuntimeError as e:
        print(f"✗ {e}")
        return 1

    try:
        ok = repo.health_check()
        print(f"• 연결 확인    : {'OK' if ok else '응답 이상'}")
    except Exception as e:
        print(f"✗ 연결 실패: {type(e).__name__}: {e}")
        print("  네트워크 정책으로 아웃바운드가 막혔거나 URL/키가 틀렸을 수 있습니다.")
        return 1

    # 1) 수집 → 저장
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
    try:
        repo.save_bundles(bundles)
        print(f"• 경기 저장    : {len(bundles)}경기 (teams/matches/offerings/odds)")
    except Exception as e:
        print(f"✗ 저장 실패: {type(e).__name__}: {e}")
        print("  → schema.sql 을 Supabase SQL Editor 에서 먼저 실행했는지 확인하세요.")
        repo.close()
        return 1

    # 2) 팀 전적 upsert/조회
    if bundles:
        t = bundles[0].match.home
        rec = TeamRecord(t.id, t.sport, "home", wins=3, draws=1, losses=1)
        repo.upsert_team_record(rec)
        got = repo.get_team_record(t.id, t.sport, "home")
        print(f"• 전적 조회    : {got.team_id} home {got.wins}승 "
              f"{got.draws}무 {got.losses}패 (승률 {got.win_rate:.2f})")

        # 3) 픽 스냅샷 저장/조회
        off = bundles[0].betman_offerings[0]
        snap = build_snapshot(
            pick_id=f"{bundles[0].match.id}:{off.outcome.value}",
            match_id=bundles[0].match.id,
            sport=bundles[0].match.sport,
            market=off.market,
            outcome=off.outcome,
            betman_odds=off.fixed_odds,
            match_features=bundles[0].features,
        )
        repo.save_pick_snapshot(asdict(snap))
        back = repo.get_pick(snap.pick_id)
        n_feat = len((back or {}).get("features") or {})
        print(f"• 픽 로그       : {snap.pick_id} 저장/조회 OK "
              f"(feature {n_feat}개 기록)")

    repo.close()
    print("\n✓ Supabase 저장 레이어 점검 완료.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
