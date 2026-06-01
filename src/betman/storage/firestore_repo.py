"""Firebase Firestore 저장 레이어 구현 (REST API 기반).

firebase-admin 의 gRPC 가 막히는 환경(SSL 인터셉트 프록시 등)에서도 동작하도록
Firestore REST API(https) + 서비스계정 OAuth2 토큰을 사용한다.

Firestore 구조:
  컬렉션 = 기존 테이블, 문서ID = 기존 PK(text). 시계열(append) 컬렉션은
  자동 문서ID 를 쓴다.

비밀키(서비스계정)는 환경변수/파일에서만 읽으며 코드/로그에 노출하지 않는다.
필요 패키지: google-auth (토큰 발급). REST 호출은 표준 urllib.
"""

from __future__ import annotations

import base64
import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, is_dataclass
from datetime import datetime
from typing import Any, Optional

from ..config import FirebaseSettings, load_firebase_settings
from ..domain.enums import Outcome, Sport
from ..domain.models import NormalizedMatchBundle, TeamRecord
from .base import MatchRepository, PickLogRepository

_SCOPE = "https://www.googleapis.com/auth/datastore"


# --------------------------------------------------------------------------- #
# 값 ↔ Firestore REST 타입 변환
# --------------------------------------------------------------------------- #
def _to_fs(value: Any) -> dict:
    """파이썬 값 → Firestore REST 'Value' 표현."""
    if value is None:
        return {"nullValue": None}
    if isinstance(value, bool):
        return {"booleanValue": value}
    if isinstance(value, int):
        return {"integerValue": str(value)}
    if isinstance(value, float):
        return {"doubleValue": value}
    if isinstance(value, str):
        return {"stringValue": value}
    if isinstance(value, datetime):
        return {"stringValue": value.isoformat()}
    if hasattr(value, "value"):  # enum
        return {"stringValue": value.value}
    if isinstance(value, (list, tuple)):
        return {"arrayValue": {"values": [_to_fs(v) for v in value]}}
    if is_dataclass(value) and not isinstance(value, type):
        return _to_fs(asdict(value))
    if isinstance(value, dict):
        return {"mapValue": {"fields": {str(k): _to_fs(v) for k, v in value.items()}}}
    return {"stringValue": str(value)}


def _from_fs(value: dict) -> Any:
    """Firestore REST 'Value' → 파이썬 값."""
    if "nullValue" in value:
        return None
    if "booleanValue" in value:
        return value["booleanValue"]
    if "integerValue" in value:
        return int(value["integerValue"])
    if "doubleValue" in value:
        return value["doubleValue"]
    if "stringValue" in value:
        return value["stringValue"]
    if "arrayValue" in value:
        return [_from_fs(v) for v in value["arrayValue"].get("values", [])]
    if "mapValue" in value:
        return {
            k: _from_fs(v)
            for k, v in value["mapValue"].get("fields", {}).items()
        }
    return None


def _doc_to_dict(doc: dict) -> dict:
    return {k: _from_fs(v) for k, v in doc.get("fields", {}).items()}


def _fields(data: dict) -> dict:
    return {str(k): _to_fs(v) for k, v in data.items()}


class FirestoreMatchRepository(MatchRepository, PickLogRepository):
    """경기/배당/전적/픽/픽로그를 Firestore REST 로 적재·조회."""

    def __init__(self, settings: FirebaseSettings | None = None) -> None:
        self.settings = settings or load_firebase_settings()
        if not self.settings.configured:
            raise RuntimeError("Firebase 미설정: 서비스계정 자격을 .env 에 설정하세요.")
        self._sa = self._load_sa_dict()
        self.project_id = (
            self.settings.project_id or self._sa.get("project_id")
        )
        if not self.project_id:
            raise RuntimeError("project_id 를 알 수 없습니다.")
        self._base = (
            f"https://firestore.googleapis.com/v1/projects/{self.project_id}"
            f"/databases/(default)/documents"
        )
        self._creds = None

    # ------------------------------------------------------------------ #
    # 인증
    # ------------------------------------------------------------------ #
    def _load_sa_dict(self) -> dict:
        s = self.settings
        if s.credentials_path:
            with open(s.credentials_path, encoding="utf-8") as fh:
                return json.load(fh)
        raw = s.credentials_json
        if s.credentials_b64:
            raw = base64.b64decode(s.credentials_b64).decode("utf-8")
        if raw:
            return json.loads(raw)
        raise RuntimeError("서비스계정 자격을 찾을 수 없습니다.")

    def _token(self) -> str:
        import google.auth.transport.requests
        from google.oauth2 import service_account

        if self._creds is None:
            self._creds = service_account.Credentials.from_service_account_info(
                self._sa, scopes=[_SCOPE]
            )
        if not self._creds.valid:
            self._creds.refresh(google.auth.transport.requests.Request())
        return self._creds.token

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._token()}",
            "Content-Type": "application/json",
        }

    def _call(self, method: str, url: str, body: dict | None = None) -> dict:
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(url, data=data, headers=self._headers(),
                                     method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            msg = e.read().decode()[:300]
            raise RuntimeError(f"Firestore {method} {e.code}: {msg}") from e

    # ------------------------------------------------------------------ #
    # 저수준 문서 ops
    # ------------------------------------------------------------------ #
    def _set(self, collection: str, doc_id: str, data: dict) -> None:
        doc_id = urllib.parse.quote(str(doc_id), safe="")
        url = f"{self._base}/{collection}/{doc_id}"
        self._call("PATCH", url, {"fields": _fields(data)})

    def _add(self, collection: str, data: dict) -> None:
        url = f"{self._base}/{collection}"
        self._call("POST", url, {"fields": _fields(data)})

    def _get(self, collection: str, doc_id: str) -> Optional[dict]:
        doc_id = urllib.parse.quote(str(doc_id), safe="")
        url = f"{self._base}/{collection}/{doc_id}"
        try:
            return _doc_to_dict(self._call("GET", url))
        except RuntimeError as e:
            if "404" in str(e):
                return None
            raise

    def _list(self, collection: str, page_size: int = 300):
        """컬렉션 전체 문서 (name, dict) 스트림."""
        token = None
        while True:
            url = f"{self._base}/{collection}?pageSize={page_size}"
            if token:
                url += f"&pageToken={token}"
            res = self._call("GET", url)
            for d in res.get("documents", []):
                yield d["name"], _doc_to_dict(d)
            token = res.get("nextPageToken")
            if not token:
                break

    def _delete_by_name(self, name: str) -> None:
        # name 은 전체 리소스 경로 → /v1/ 뒤만 사용
        url = f"https://firestore.googleapis.com/v1/{name}"
        self._call("DELETE", url)

    def _delete_collection(self, collection: str) -> None:
        for name, _ in list(self._list(collection)):
            self._delete_by_name(name)

    # ------------------------------------------------------------------ #
    # MatchRepository
    # ------------------------------------------------------------------ #
    def save_bundles(self, bundles: list[NormalizedMatchBundle]) -> None:
        teams: dict[str, dict] = {}
        for b in bundles:
            m = b.match
            for t in (m.home, m.away):
                teams[t.id] = {"id": t.id, "name": t.name, "sport": t.sport.value}
            self._set("matches", m.id, {
                "id": m.id, "sport": m.sport.value, "league": m.league,
                "home_team_id": m.home.id, "away_team_id": m.away.id,
                "start_time": m.start_time.isoformat(), "status": m.status.value,
            })
            for o in b.betman_offerings:
                self._add("betman_offerings", {
                    "match_id": o.match_id, "round_no": o.round_no,
                    "market": o.market.value, "outcome": o.outcome.value,
                    "fixed_odds": o.fixed_odds, "sales_open": o.sales_open,
                })
            for q in b.overseas_odds:
                self._add("overseas_odds", {
                    "match_id": m.id, "bookmaker": q.bookmaker,
                    "market": q.market.value, "outcome": q.outcome.value,
                    "decimal_odds": q.decimal_odds,
                    "captured_at": q.captured_at.isoformat(),
                })
        for t in teams.values():
            self._set("teams", t["id"], t)

    def get_team_record(
        self, team_id: str, sport: Sport, venue: str = "overall"
    ) -> TeamRecord:
        r = self._get("team_records", f"{team_id}__{venue}")
        if not r:
            return TeamRecord(team_id=team_id, sport=sport, venue=venue)
        return TeamRecord(
            team_id=r["team_id"], sport=Sport(r["sport"]), venue=r["venue"],
            wins=r["wins"], draws=r["draws"], losses=r["losses"],
        )

    def upsert_team_record(self, record: TeamRecord) -> None:
        self._set("team_records", f"{record.team_id}__{record.venue}", {
            "team_id": record.team_id, "sport": record.sport.value,
            "venue": record.venue, "wins": record.wins, "draws": record.draws,
            "losses": record.losses, "updated_at": datetime.now().isoformat(),
        })

    # ------------------------------------------------------------------ #
    # picks
    # ------------------------------------------------------------------ #
    def save_picks(self, rows: list[dict]) -> None:
        for r in rows:
            self._set("picks", r["pick_id"], r)

    def replace_all_picks(self, rows: list[dict]) -> None:
        self._delete_collection("picks")
        self.save_picks(rows)

    # ------------------------------------------------------------------ #
    # PickLogRepository
    # ------------------------------------------------------------------ #
    def save_pick_snapshot(self, snapshot: dict) -> None:
        self._set("pick_logs", str(snapshot["pick_id"]), snapshot)

    def record_pick_result(
        self, pick_id: str, result_outcome: Outcome, hit: bool
    ) -> None:
        existing = self._get("pick_logs", pick_id) or {}
        existing.update({"result_outcome": result_outcome.value, "hit": hit})
        self._set("pick_logs", pick_id, existing)

    def get_pick(self, pick_id: str) -> Optional[dict]:
        return self._get("pick_logs", pick_id)

    # ------------------------------------------------------------------ #
    def read_collection(self, collection: str) -> list[dict]:
        """컬렉션 전체를 dict 리스트로 (콜렉터/마이그레이션용)."""
        return [d for _, d in self._list(collection)]

    def health_check(self) -> bool:
        # 임의 컬렉션 1건 조회 시도 (없어도 200/empty 면 OK)
        url = f"{self._base}/__healthcheck__?pageSize=1"
        self._call("GET", url)
        return True

    def close(self) -> None:
        pass

    def __enter__(self) -> "FirestoreMatchRepository":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
