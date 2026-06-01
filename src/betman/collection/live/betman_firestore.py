"""Firestore betman_manual_odds 컬렉션 → 베트맨 발매 배당 수집.

대시보드(/betman 페이지)에서 붙여넣어 저장한 수동 배당을 읽어, 팀명(aliases)으로
실제 경기와 매칭한다. (Supabase 콜렉터의 Firestore 버전)

웹 입력 → Firestore → (이 콜렉터) → 분석 파이프라인.
"""

from __future__ import annotations

from pathlib import Path

from ...config import FirebaseSettings, load_firebase_settings
from ...domain.enums import MarketType, Outcome
from ...domain.models import BetmanOffering, Match
from ..base import BetmanCollector
from .betman_csv import _load_aliases, _norm

_OUTCOME = {
    "home": Outcome.HOME, "draw": Outcome.DRAW, "away": Outcome.AWAY,
    "over": Outcome.OVER, "under": Outcome.UNDER,
    "odd": Outcome.ODD, "even": Outcome.EVEN,
}
_MARKET = {
    "match_1x2": MarketType.MATCH_1X2, "moneyline": MarketType.MONEYLINE,
    "handicap": MarketType.HANDICAP, "totals": MarketType.TOTALS,
    "sum": MarketType.SUM,
}


class BetmanFirestoreCollector(BetmanCollector):
    """betman_manual_odds 컬렉션을 한 번 읽어 캐시하고, 경기별 팀명으로 매칭."""

    def __init__(
        self,
        settings: FirebaseSettings | None = None,
        aliases_path: str | Path | None = "data/betman/aliases.json",
        round_no: str | None = None,
    ) -> None:
        self.settings = settings or load_firebase_settings()
        self.aliases = _load_aliases(Path(aliases_path) if aliases_path else None)
        self.round_no = round_no
        self._rows: list[dict] = []
        self._loaded = False

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        if not self.settings.configured:
            return
        try:
            from ...storage.firestore_repo import FirestoreMatchRepository

            repo = FirestoreMatchRepository(self.settings)
            rows = repo.read_collection("betman_manual_odds")
            # 클라이언트 측 필터(REST 전체 읽기 후)
            rows = [r for r in rows if r.get("sales_open", True)]
            if self.round_no:
                rows = [r for r in rows if str(r.get("round_no")) == self.round_no]
            self._rows = rows
        except Exception:
            self._rows = []

    def _alias(self, name: str) -> str:
        return self.aliases.get(_norm(name), name)

    def _key(self, a: str, b: str) -> tuple[str, str]:
        return (_norm(self._alias(a)), _norm(self._alias(b)))

    def collect_offerings(self, match: Match) -> list[BetmanOffering]:
        self._ensure_loaded()
        want = self._key(match.home.name, match.away.name)
        default_market = (
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
            market = _MARKET.get(r.get("market") or "", default_market)
            line = r.get("line")
            out.append(
                BetmanOffering(
                    match_id=match.id,
                    round_no=str(r.get("round_no", "")),
                    market=market,
                    outcome=oc,
                    fixed_odds=float(r["odds"]),
                    sales_open=bool(r.get("sales_open", True)),
                    line=float(line) if line is not None else None,
                    game_no=str(r.get("game_no", "")),
                )
            )
        return out
