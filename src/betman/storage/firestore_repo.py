"""Firebase Firestore 저장 레이어 구현.

Supabase(Postgres) 대신 Firestore(NoSQL 문서 DB)에 적재/조회한다.
Firestore 구조:
  컬렉션 = 기존 테이블, 문서ID = 기존 PK(text). 시계열(append) 테이블은
  자동생성 문서ID 를 쓴다.

  teams/{team_id}            picks/{pick_id}
  matches/{match_id}         pick_logs/{pick_id}
  team_records/{tid__venue}  betman_offerings/{auto}
  overseas_odds/{auto}       bets/{auto}
  betman_manual_odds/{auto}

비밀키(서비스계정)는 환경변수/파일에서만 읽으며 코드/로그에 노출하지 않는다.
firebase-admin SDK 가 필요하다: pip install firebase-admin
"""

from __future__ import annotations

import base64
import json
from dataclasses import asdict, is_dataclass
from datetime import datetime
from typing import Any, Optional

from ..config import FirebaseSettings, load_firebase_settings
from ..domain.enums import Outcome, Sport
from ..domain.models import NormalizedMatchBundle, TeamRecord
from .base import MatchRepository, PickLogRepository

# 모듈 전역으로 앱 1회만 초기화(중복 init 방지)
_APP = None


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (Sport, Outcome)) or hasattr(value, "value"):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return {k: _jsonable(v) for k, v in asdict(value).items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    return str(value)


def _load_credentials(settings: FirebaseSettings):
    from firebase_admin import credentials

    if settings.credentials_path:
        return credentials.Certificate(settings.credentials_path)
    raw = settings.credentials_json
    if settings.credentials_b64:
        raw = base64.b64decode(settings.credentials_b64).decode("utf-8")
    if raw:
        return credentials.Certificate(json.loads(raw))
    raise RuntimeError(
        "Firebase 서비스계정 미설정: GOOGLE_APPLICATION_CREDENTIALS(파일경로) 또는 "
        "FIREBASE_SERVICE_ACCOUNT(JSON) 또는 FIREBASE_SERVICE_ACCOUNT_BASE64 를 설정하세요."
    )


class FirestoreMatchRepository(MatchRepository, PickLogRepository):
    """경기/배당/전적/픽/픽로그를 Firestore에 적재·조회."""

    def __init__(self, settings: FirebaseSettings | None = None) -> None:
        global _APP
        self.settings = settings or load_firebase_settings()
        if not self.settings.configured:
            raise RuntimeError(
                "Firebase 미설정: 서비스계정 자격을 .env 에 설정하세요."
            )
        import firebase_admin
        from firebase_admin import firestore

        if _APP is None:
            cred = _load_credentials(self.settings)
            opts = {"projectId": self.settings.project_id} if self.settings.project_id else None
            _APP = firebase_admin.initialize_app(cred, opts)
        self._db = firestore.client()

    # ------------------------------------------------------------------ #
    # 저수준 helper
    # ------------------------------------------------------------------ #
    def _set(self, collection: str, doc_id: str, data: dict) -> None:
        self._db.collection(collection).document(doc_id).set(_jsonable(data))

    def _batch_set(self, collection: str, rows: list[dict], id_key: str) -> None:
        """문서ID = row[id_key]. 500개씩 배치 커밋."""
        for i in range(0, len(rows), 450):
            batch = self._db.batch()
            for r in rows[i:i + 450]:
                ref = self._db.collection(collection).document(str(r[id_key]))
                batch.set(ref, _jsonable(r))
            batch.commit()

    def _batch_add(self, collection: str, rows: list[dict]) -> None:
        """자동생성 ID 로 append (시계열). 450개씩 배치."""
        for i in range(0, len(rows), 450):
            batch = self._db.batch()
            for r in rows[i:i + 450]:
                ref = self._db.collection(collection).document()
                batch.set(ref, _jsonable(r))
            batch.commit()

    # ------------------------------------------------------------------ #
    # MatchRepository
    # ------------------------------------------------------------------ #
    def save_bundles(self, bundles: list[NormalizedMatchBundle]) -> None:
        teams: dict[str, dict] = {}
        matches: list[dict] = []
        offerings: list[dict] = []
        odds: list[dict] = []

        for b in bundles:
            m = b.match
            for t in (m.home, m.away):
                teams[t.id] = {"id": t.id, "name": t.name, "sport": t.sport.value}
            matches.append({
                "id": m.id,
                "sport": m.sport.value,
                "league": m.league,
                "home_team_id": m.home.id,
                "away_team_id": m.away.id,
                "start_time": m.start_time.isoformat(),
                "status": m.status.value,
            })
            for o in b.betman_offerings:
                offerings.append({
                    "match_id": o.match_id, "round_no": o.round_no,
                    "market": o.market.value, "outcome": o.outcome.value,
                    "fixed_odds": o.fixed_odds, "sales_open": o.sales_open,
                })
            for q in b.overseas_odds:
                odds.append({
                    "match_id": m.id, "bookmaker": q.bookmaker,
                    "market": q.market.value, "outcome": q.outcome.value,
                    "decimal_odds": q.decimal_odds,
                    "captured_at": q.captured_at.isoformat(),
                })

        self._batch_set("teams", list(teams.values()), id_key="id")
        self._batch_set("matches", matches, id_key="id")
        self._batch_add("betman_offerings", offerings)
        self._batch_add("overseas_odds", odds)

    def get_team_record(
        self, team_id: str, sport: Sport, venue: str = "overall"
    ) -> TeamRecord:
        doc = self._db.collection("team_records").document(
            f"{team_id}__{venue}"
        ).get()
        if not doc.exists:
            return TeamRecord(team_id=team_id, sport=sport, venue=venue)
        r = doc.to_dict()
        return TeamRecord(
            team_id=r["team_id"], sport=Sport(r["sport"]), venue=r["venue"],
            wins=r["wins"], draws=r["draws"], losses=r["losses"],
        )

    def upsert_team_record(self, record: TeamRecord) -> None:
        self._set(
            "team_records", f"{record.team_id}__{record.venue}",
            {
                "team_id": record.team_id, "sport": record.sport.value,
                "venue": record.venue, "wins": record.wins,
                "draws": record.draws, "losses": record.losses,
                "updated_at": datetime.now().isoformat(),
            },
        )

    # ------------------------------------------------------------------ #
    # picks (대시보드용)
    # ------------------------------------------------------------------ #
    def save_picks(self, rows: list[dict]) -> None:
        self._batch_set("picks", rows, id_key="pick_id")

    def replace_all_picks(self, rows: list[dict]) -> None:
        """기존 picks 전체 삭제 후 새로 적재(분석 갱신용)."""
        self._delete_collection("picks")
        self._batch_set("picks", rows, id_key="pick_id")

    def _delete_collection(self, collection: str, page: int = 300) -> None:
        col = self._db.collection(collection)
        while True:
            docs = list(col.limit(page).stream())
            if not docs:
                break
            batch = self._db.batch()
            for d in docs:
                batch.delete(d.reference)
            batch.commit()

    # ------------------------------------------------------------------ #
    # PickLogRepository
    # ------------------------------------------------------------------ #
    def save_pick_snapshot(self, snapshot: dict) -> None:
        self._set("pick_logs", str(snapshot["pick_id"]), snapshot)

    def record_pick_result(
        self, pick_id: str, result_outcome: Outcome, hit: bool
    ) -> None:
        self._db.collection("pick_logs").document(pick_id).set(
            {"result_outcome": result_outcome.value, "hit": hit}, merge=True
        )

    def get_pick(self, pick_id: str) -> Optional[dict]:
        doc = self._db.collection("pick_logs").document(pick_id).get()
        return doc.to_dict() if doc.exists else None

    # ------------------------------------------------------------------ #
    def health_check(self) -> bool:
        # 컬렉션 목록 조회로 연결 확인
        next(iter(self._db.collections()), None)
        return True

    def close(self) -> None:
        pass

    def __enter__(self) -> "FirestoreMatchRepository":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
