"""Supabase(Postgres) 저장 레이어 구현.

PostgREST REST API + service_role 키로 데이터를 적재/조회한다.
스키마(테이블)는 schema.sql 을 Supabase SQL Editor 에서 1회 실행해 만든다
(REST로는 DDL 불가).

비밀키는 환경변수/.env 에서만 읽으며 코드/로그에 노출하지 않는다.
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime
from typing import Any, Optional

from ..config import SupabaseSettings, load_supabase_settings
from ..domain.enums import Outcome, Sport
from ..domain.models import NormalizedMatchBundle, TeamRecord
from .base import MatchRepository, PickLogRepository


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


class SupabaseMatchRepository(MatchRepository, PickLogRepository):
    """경기/배당/전적/픽로그를 Supabase에 적재·조회."""

    def __init__(self, settings: SupabaseSettings | None = None) -> None:
        self.settings = settings or load_supabase_settings()
        if not self.settings.configured:
            raise RuntimeError(
                "Supabase 미설정: .env 에 SUPABASE_URL 과 "
                "SUPABASE_SERVICE_ROLE_KEY(또는 ANON_KEY)를 넣어주세요."
            )
        # httpx 는 호출 시점에 import (수집 단계는 httpx 없이도 동작)
        import httpx

        key = self.settings.write_key
        self._client = httpx.Client(
            base_url=f"{self.settings.url}/rest/v1",
            headers={
                "apikey": key,
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )

    # ------------------------------------------------------------------ #
    # 저수준 helper
    # ------------------------------------------------------------------ #
    def _upsert(self, table: str, rows: list[dict], on_conflict: str) -> None:
        if not rows:
            return
        resp = self._client.post(
            f"/{table}",
            params={"on_conflict": on_conflict},
            headers={"Prefer": "resolution=merge-duplicates,return=minimal"},
            json=rows,
        )
        resp.raise_for_status()

    def _insert(self, table: str, rows: list[dict]) -> None:
        if not rows:
            return
        resp = self._client.post(
            f"/{table}",
            headers={"Prefer": "return=minimal"},
            json=rows,
        )
        resp.raise_for_status()

    def _select(self, table: str, params: dict) -> list[dict]:
        resp = self._client.get(f"/{table}", params=params)
        resp.raise_for_status()
        return resp.json()

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
            matches.append(
                {
                    "id": m.id,
                    "sport": m.sport.value,
                    "league": m.league,
                    "home_team_id": m.home.id,
                    "away_team_id": m.away.id,
                    "start_time": m.start_time.isoformat(),
                    "status": m.status.value,
                }
            )
            for o in b.betman_offerings:
                offerings.append(
                    {
                        "match_id": o.match_id,
                        "round_no": o.round_no,
                        "market": o.market.value,
                        "outcome": o.outcome.value,
                        "fixed_odds": o.fixed_odds,
                        "sales_open": o.sales_open,
                    }
                )
            for q in b.overseas_odds:
                odds.append(
                    {
                        "match_id": m.id,
                        "bookmaker": q.bookmaker,
                        "market": q.market.value,
                        "outcome": q.outcome.value,
                        "decimal_odds": q.decimal_odds,
                        "captured_at": q.captured_at.isoformat(),
                    }
                )

        # 참조 무결성 순서: teams → matches → (offerings, odds)
        self._upsert("teams", list(teams.values()), on_conflict="id")
        self._upsert("matches", matches, on_conflict="id")
        # 배당/발매는 시계열 스냅샷 → 누적 insert
        self._insert("betman_offerings", offerings)
        self._insert("overseas_odds", odds)

    def get_team_record(
        self, team_id: str, sport: Sport, venue: str = "overall"
    ) -> TeamRecord:
        rows = self._select(
            "team_records",
            {
                "team_id": f"eq.{team_id}",
                "venue": f"eq.{venue}",
                "select": "team_id,sport,venue,wins,draws,losses",
                "limit": "1",
            },
        )
        if not rows:
            return TeamRecord(team_id=team_id, sport=sport, venue=venue)
        r = rows[0]
        return TeamRecord(
            team_id=r["team_id"],
            sport=Sport(r["sport"]),
            venue=r["venue"],
            wins=r["wins"],
            draws=r["draws"],
            losses=r["losses"],
        )

    def upsert_team_record(self, record: TeamRecord) -> None:
        self._upsert(
            "team_records",
            [
                {
                    "team_id": record.team_id,
                    "sport": record.sport.value,
                    "venue": record.venue,
                    "wins": record.wins,
                    "draws": record.draws,
                    "losses": record.losses,
                    "updated_at": datetime.now().isoformat(),
                }
            ],
            on_conflict="team_id,venue",
        )

    # ------------------------------------------------------------------ #
    # PickLogRepository
    # ------------------------------------------------------------------ #
    def save_picks(self, rows: list[dict]) -> None:
        """분석 결과 픽(대시보드 표시용)을 picks 테이블에 upsert."""
        self._upsert(
            "picks", [_jsonable(r) for r in rows], on_conflict="pick_id"
        )

    def save_pick_snapshot(self, snapshot: dict) -> None:
        self._upsert("pick_logs", [_jsonable(snapshot)], on_conflict="pick_id")

    def record_pick_result(
        self, pick_id: str, result_outcome: Outcome, hit: bool
    ) -> None:
        resp = self._client.patch(
            "/pick_logs",
            params={"pick_id": f"eq.{pick_id}"},
            headers={"Prefer": "return=minimal"},
            json={"result_outcome": result_outcome.value, "hit": hit},
        )
        resp.raise_for_status()

    def get_pick(self, pick_id: str) -> Optional[dict]:
        rows = self._select(
            "pick_logs", {"pick_id": f"eq.{pick_id}", "select": "*", "limit": "1"}
        )
        return rows[0] if rows else None

    # ------------------------------------------------------------------ #
    def health_check(self) -> bool:
        """REST 엔드포인트 도달 가능 여부."""
        resp = self._client.get("/")
        return resp.status_code < 500

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "SupabaseMatchRepository":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
