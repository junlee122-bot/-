"""베트맨 발매·고정배당 CSV/JSON 수동 입력 어댑터.

베트맨(프로토 승부식)은 공식 배당 API가 없으므로, 회차별 발매표를 손으로
CSV(또는 JSON)에 적어 넣으면 이 어댑터가 읽어 BetmanOffering 으로 변환한다.
실제 베트맨 고정배당이 들어와야 edge/EV 가 의미를 갖는다.

매칭 전략(중요):
  The Odds API 경기 id 와 베트맨 발매표를 잇는 공통 키가 없으므로,
  팀명(또는 별칭)으로 매칭한다. CSV의 home/away 는 The Odds API 의 영문
  팀명과 같거나, aliases 파일로 한글↔영문을 매핑할 수 있다.

CSV 컬럼(헤더 필수):
  round_no,sport,home,away,market,outcome,odds[,sales_open]
    - sport   : soccer|baseball|basketball|volleyball|hockey|esports
    - market  : 비우면 종목으로 자동(축구/하키=match_1x2, 그 외=moneyline)
    - outcome : home|draw|away
    - odds    : 베트맨 고정배당(십진). 예 2.05
    - sales_open : true/false (기본 true)

예) data/betman/round_2610.csv
  round_no,sport,home,away,market,outcome,odds
  2610,baseball,Samsung Lions,Doosan Bears,,home,1.95
  2610,baseball,Samsung Lions,Doosan Bears,,away,1.78
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from ...domain.enums import MarketType, Outcome, Sport
from ...domain.models import BetmanOffering, Match
from ..base import BetmanCollector

_OUTCOME = {
    "home": Outcome.HOME,
    "draw": Outcome.DRAW,
    "away": Outcome.AWAY,
    "h": Outcome.HOME,
    "d": Outcome.DRAW,
    "a": Outcome.AWAY,
}
_MARKET = {
    "match_1x2": MarketType.MATCH_1X2,
    "1x2": MarketType.MATCH_1X2,
    "moneyline": MarketType.MONEYLINE,
    "ml": MarketType.MONEYLINE,
    "h2h": MarketType.MONEYLINE,
}


def _norm(s: str) -> str:
    """팀명 매칭용 정규화: 소문자 + 공백/기호 제거."""
    return "".join(ch for ch in s.lower() if ch.isalnum())


class _Row:
    __slots__ = ("sport", "home", "away", "round_no", "market", "outcome",
                 "odds", "sales_open")

    def __init__(self, d: dict) -> None:
        self.sport = Sport((d.get("sport") or "").strip().lower())
        self.home = (d.get("home") or "").strip()
        self.away = (d.get("away") or "").strip()
        self.round_no = (d.get("round_no") or "").strip()
        oc = (d.get("outcome") or "").strip().lower()
        if oc not in _OUTCOME:
            raise ValueError(f"알 수 없는 outcome: {oc!r}")
        self.outcome = _OUTCOME[oc]
        mk = (d.get("market") or "").strip().lower()
        if mk:
            if mk not in _MARKET:
                raise ValueError(f"알 수 없는 market: {mk!r}")
            self.market = _MARKET[mk]
        else:
            self.market = (
                MarketType.MATCH_1X2 if self.sport.has_draw
                else MarketType.MONEYLINE
            )
        self.odds = float(d["odds"])
        so = str(d.get("sales_open", "true")).strip().lower()
        self.sales_open = so not in ("false", "0", "no", "n", "")


def _load_rows(path: Path) -> list[_Row]:
    rows: list[_Row] = []
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        records = data if isinstance(data, list) else data.get("offerings", [])
        for d in records:
            rows.append(_Row(d))
    else:  # CSV
        with path.open(encoding="utf-8-sig", newline="") as fh:
            for d in csv.DictReader(fh):
                if not (d.get("home") and d.get("away") and d.get("odds")):
                    continue
                rows.append(_Row(d))
    return rows


def _load_aliases(path: Path | None) -> dict[str, str]:
    """별칭 파일(JSON): {"한화 이글스":"Hanwha Eagles", ...} → 정규화 키 매핑."""
    if not path or not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {_norm(k): v for k, v in raw.items()}


class BetmanCsvCollector(BetmanCollector):
    """CSV/JSON 디렉터리에서 베트맨 발매표를 읽어 경기별로 매칭."""

    def __init__(
        self,
        source_dir: str | Path = "data/betman",
        aliases_path: str | Path | None = "data/betman/aliases.json",
    ) -> None:
        self.source_dir = Path(source_dir)
        self.aliases = _load_aliases(
            Path(aliases_path) if aliases_path else None
        )
        self._rows: list[_Row] = []
        self._loaded = False

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._rows = []
        if self.source_dir.exists():
            for p in sorted(self.source_dir.iterdir()):
                if p.suffix.lower() in (".csv", ".json") and p.name != "aliases.json":
                    try:
                        self._rows.extend(_load_rows(p))
                    except (ValueError, KeyError, json.JSONDecodeError):
                        # 한 파일이 깨져도 나머지는 살림
                        continue
        self._loaded = True

    def _alias(self, name: str) -> str:
        return self.aliases.get(_norm(name), name)

    def _match_key(self, a: str, b: str) -> tuple[str, str]:
        return (_norm(self._alias(a)), _norm(self._alias(b)))

    def collect_offerings(self, match: Match) -> list[BetmanOffering]:
        self._ensure_loaded()
        want = self._match_key(match.home.name, match.away.name)
        out: list[BetmanOffering] = []
        for r in self._rows:
            if r.sport != match.sport:
                continue
            if self._match_key(r.home, r.away) != want:
                continue
            out.append(
                BetmanOffering(
                    match_id=match.id,
                    round_no=r.round_no,
                    market=r.market,
                    outcome=r.outcome,
                    fixed_odds=r.odds,
                    sales_open=r.sales_open,
                )
            )
        return out
