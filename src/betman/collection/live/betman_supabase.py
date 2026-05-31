"""Supabase betman_manual_odds 테이블 → 베트맨 발매 배당 수집.

대시보드(/betman 페이지)에서 붙여넣어 저장한 수동 배당을 읽어, 팀명(aliases)으로
실제 경기와 매칭한다. CSV 어댑터(betman_csv)와 같은 매칭 로직을 쓴다.

웹 입력 → Supabase → (이 콜렉터) → 분석 파이프라인 으로 이어지는 경로.
"""

from __future__ import annotations

import json
from pathlib import Path

from ...config import SupabaseSettings, load_supabase_settings
from ...domain.enums import MarketType, Outcome, Sport
from ...domain.models import BetmanOffering, Match
from ..base import BetmanCollector
from .betman_csv import _load_aliases, _norm

_OUTCOME = {"home": Outcome.HOME, "draw": Outcome.DRAW, "away": Outcome.AWAY}


class BetmanSupabaseCollector(BetmanCollector):
    """betman_manual_odds 를 한 번 읽어 캐시하고, 경기별 팀명으로 매칭."""

    def __init__(
        self,
        settings: SupabaseSettings | None = None,
        aliases_path: str | Path | None = "data/betman/aliases.json",
        round_no: str | None = None,
    ) -> None:
        self.settings = settings or load_supabase_settings()
        self.aliases = _load_aliases(Path(aliases_path) if aliases_path else None)
        self.round_no = round_no          # 지정 시 해당 회차만
        self._rows: list[dict] = []
        self._loaded = False

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        if not self.settings.configured:
            return
        import httpx

        key = self.settings.write_key
        params = {"select": "*", "sales_open": "eq.true"}
        if self.round_no:
            params["round_no"] = f"eq.{self.round_no}"
        try:
            resp = httpx.get(
                f"{self.settings.url}/rest/v1/betman_manual_odds",
                params=params,
                headers={"apikey": key, "Authorization": f"Bearer {key}"},
                timeout=30.0,
            )
            resp.raise_for_status()
            self._rows = resp.json()
        except Exception:
            # 테이블이 없거나 네트워크 문제 → 빈 결과(파이프라인은 계속)
            self._rows = []

    def _alias(self, name: str) -> str:
        return self.aliases.get(_norm(name), name)

    def _key(self, a: str, b: str) -> tuple[str, str]:
        return (_norm(self._alias(a)), _norm(self._alias(b)))

    def collect_offerings(self, match: Match) -> list[BetmanOffering]:
        self._ensure_loaded()
        want = self._key(match.home.name, match.away.name)
        market = (
            MarketType.MATCH_1X2 if match.sport.has_draw else MarketType.MONEYLINE
        )
        out: list[BetmanOffering] = []
        for r in self._rows:
            if r.get("sport") != match.sport.value:
                continue
            if self._key(r.get("home", ""), r.get("away", "")) != want:
                continue
            oc = _OUTCOME.get(r.get("outcome", ""))
            if oc is None:
                continue
            out.append(
                BetmanOffering(
                    match_id=match.id,
                    round_no=str(r.get("round_no", "")),
                    market=market,
                    outcome=oc,
                    fixed_odds=float(r["odds"]),
                    sales_open=bool(r.get("sales_open", True)),
                )
            )
        return out
