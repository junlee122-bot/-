"""Firebase Firestore 저장 레이어 점검/스모크 테스트.

사전: .env 에 Firebase 서비스계정 자격 설정(README 참고).
실행:
    python -m scripts.init_firestore

수행: 연결 확인 → mock 경기 수집 → 저장 → 팀 전적 set/get → 픽 저장/조회.

참고: Firestore 는 스키마 생성이 불필요하다(컬렉션/문서는 쓰는 순간 생성).
단, 대시보드의 정렬 쿼리(picks orderBy value_score)는 단일 필드라 자동 인덱스로
충분하다. 복합 쿼리를 추가하면 콘솔에서 안내하는 인덱스를 만들면 된다.
"""

from __future__ import annotations

import sys
from dataclasses import asdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from betman.config import DEFAULT_CONFIG, load_firebase_settings  # noqa: E402
from betman.collection.mock.mock_betman import MockBetmanCollector  # noqa: E402
from betman.collection.mock.mock_features import MockFeatureCollector  # noqa: E402
from betman.collection.mock.mock_match import MockMatchCollector  # noqa: E402
from betman.collection.mock.mock_news import MockNewsCollector  # noqa: E402
from betman.collection.mock.mock_odds import MockOddsCollector  # noqa: E402
from betman.collection.pipeline import DataCollectionPipeline  # noqa: E402
from betman.domain.models import CollectionRequest, TeamRecord  # noqa: E402
from betman.analysis.provenance import build_snapshot  # noqa: E402


def main() -> int:
    settings = load_firebase_settings()
    if not settings.configured:
        print("✗ Firebase 미설정. .env 에 서비스계정 자격을 넣어주세요:")
        print("    GOOGLE_APPLICATION_CREDENTIALS=서비스계정.json  또는")
        print("    FIREBASE_SERVICE_ACCOUNT_BASE64=<base64>")
        return 1

    try:
        from betman.storage.firestore_repo import FirestoreMatchRepository
        repo = FirestoreMatchRepository(settings)
    except Exception as e:
        print(f"✗ 저장소 초기화 실패: {e}")
        return 1

    try:
        repo.health_check()
        print("• 연결 확인    : OK")
    except Exception as e:
        print(f"✗ 연결 실패: {type(e).__name__}: {e}")
        return 1

    pipeline = DataCollectionPipeline(
        MockMatchCollector(), MockOddsCollector(), MockBetmanCollector(),
        MockNewsCollector(), MockFeatureCollector(),
    )
    bundles = pipeline.run(
        CollectionRequest(sports=DEFAULT_CONFIG.sports, target_date=date(2026, 6, 1))
    )
    try:
        repo.save_bundles(bundles)
        print(f"• 경기 저장    : {len(bundles)}경기 (teams/matches/offerings/odds)")
    except Exception as e:
        print(f"✗ 저장 실패: {type(e).__name__}: {e}")
        return 1

    if bundles:
        t = bundles[0].match.home
        repo.upsert_team_record(TeamRecord(t.id, t.sport, "home", 3, 1, 1))
        got = repo.get_team_record(t.id, t.sport, "home")
        print(f"• 전적 조회    : {got.team_id} {got.wins}승{got.draws}무{got.losses}패")

        off = bundles[0].betman_offerings[0]
        snap = build_snapshot(
            pick_id=f"{bundles[0].match.id}:{off.outcome.value}",
            match_id=bundles[0].match.id, sport=bundles[0].match.sport,
            market=off.market, outcome=off.outcome, betman_odds=off.fixed_odds,
            match_features=bundles[0].features,
        )
        repo.save_pick_snapshot(asdict(snap))
        back = repo.get_pick(snap.pick_id)
        n = len((back or {}).get("features") or {})
        print(f"• 픽 로그       : {snap.pick_id} 저장/조회 OK (feature {n}개)")

    repo.close()
    print("\n✓ Firestore 저장 레이어 점검 완료.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
