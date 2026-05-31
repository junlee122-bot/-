"""The Odds API (v4) 어댑터 — 해외 배당 + 경기 목록.

무료 티어는 월 500요청이라 쿼터 절약이 핵심이다:
  - 종목(sport_key)당 1회만 호출하고 TTL 동안 캐시한다.
  - 한 번의 odds 응답에 '경기 + 모든 북메이커 배당'이 함께 오므로,
    MatchCollector(경기 목록)와 OddsCollector(배당)가 같은 캐시를 공유한다.

스키마(v4 /sports/{key}/odds):
  [{ id, sport_key, commence_time, home_team, away_team,
     bookmakers:[{ key, title, last_update,
                   markets:[{ key:"h2h", outcomes:[{name, price}] }] }] }]

h2h 마켓: outcome name 이 home_team/away_team 와 같으면 HOME/AWAY,
"Draw" 면 DRAW 로 매핑(축구 3갈래).

표준 라이브러리(urllib)만 사용. httpx 불필요.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone

from ...config import ODDS_API_SPORT_KEYS, OddsApiSettings, load_odds_api_settings
from ...domain.enums import MarketType, MatchStatus, Outcome, Sport
from ...domain.models import InjuryNote, Lineup, Match, OddsQuote, Team
from ..base import MatchCollector, OddsCollector

_BASE = "https://api.the-odds-api.com/v4"


class OddsApiError(RuntimeError):
    pass


class OddsApiClient:
    """저수준 호출 + 캐시 + 쿼터 추적. 종목당 1회 호출 후 이벤트를 캐시."""

    def __init__(self, settings: OddsApiSettings | None = None) -> None:
        self.settings = settings or load_odds_api_settings()
        if not self.settings.configured:
            raise OddsApiError(
                "ODDS_API_KEY 미설정: .env 에 ODDS_API_KEY 를 넣어주세요."
            )
        # sport_key -> (fetched_at, events)
        self._cache: dict[str, tuple[float, list[dict]]] = {}
        self.requests_remaining: int | None = None
        self.requests_used: int | None = None

    def _get_json(self, path: str, params: dict) -> list[dict]:
        params = {**params, "apiKey": self.settings.api_key}
        url = f"{_BASE}{path}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=25) as resp:
                self.requests_remaining = _int_or_none(
                    resp.headers.get("x-requests-remaining")
                )
                self.requests_used = _int_or_none(
                    resp.headers.get("x-requests-used")
                )
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:  # type: ignore[attr-defined]
            body = e.read().decode("utf-8", "ignore")[:200]
            raise OddsApiError(f"HTTP {e.code}: {body}") from e
        except Exception as e:  # noqa: BLE001
            raise OddsApiError(f"{type(e).__name__}: {e}") from e

    def events_for_sport(self, sport: Sport) -> list[dict]:
        """우리 Sport 에 매핑된 모든 sport_key 의 이벤트를 합쳐 반환(캐시)."""
        out: list[dict] = []
        for key in ODDS_API_SPORT_KEYS.get(sport, []):
            out.extend(self._events_for_key(key))
        return out

    def _events_for_key(self, sport_key: str) -> list[dict]:
        now = time.time()
        cached = self._cache.get(sport_key)
        if cached and now - cached[0] < self.settings.cache_ttl_sec:
            return cached[1]
        events = self._get_json(
            f"/sports/{sport_key}/odds/",
            {
                "regions": self.settings.regions,
                "markets": "h2h",
                "oddsFormat": "decimal",
            },
        )
        events = events if isinstance(events, list) else []
        self._cache[sport_key] = (now, events)
        return events


def _int_or_none(v: str | None) -> int | None:
    try:
        return int(v) if v is not None else None
    except ValueError:
        return None


def _parse_dt(s: str) -> datetime:
    # commence_time 예: "2026-05-31T18:00:00Z"
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def parse_event_to_match(event: dict, sport: Sport) -> Match:
    home = event["home_team"]
    away = event["away_team"]
    return Match(
        id=event["id"],
        sport=sport,
        league=event.get("sport_title") or event.get("sport_key", ""),
        home=Team(id=f"{sport.value}:{home}", name=home, sport=sport),
        away=Team(id=f"{sport.value}:{away}", name=away, sport=sport),
        start_time=_parse_dt(event["commence_time"]),
        status=MatchStatus.SCHEDULED,
    )


def _map_outcome(name: str, home: str, away: str) -> Outcome | None:
    if name == home:
        return Outcome.HOME
    if name == away:
        return Outcome.AWAY
    if name.lower() == "draw":
        return Outcome.DRAW
    return None


def parse_event_to_quotes(event: dict, sport: Sport) -> list[OddsQuote]:
    home, away = event["home_team"], event["away_team"]
    market_type = MarketType.MATCH_1X2 if sport.has_draw else MarketType.MONEYLINE
    captured = datetime.now(timezone.utc)
    quotes: list[OddsQuote] = []
    for book in event.get("bookmakers", []):
        for market in book.get("markets", []):
            if market.get("key") != "h2h":
                continue
            for o in market.get("outcomes", []):
                oc = _map_outcome(o.get("name", ""), home, away)
                price = o.get("price")
                if oc is None or not price:
                    continue
                quotes.append(
                    OddsQuote(
                        bookmaker=book["key"],
                        market=market_type,
                        outcome=oc,
                        decimal_odds=float(price),
                        captured_at=captured,
                    )
                )
    return quotes


class OddsApiMatchCollector(MatchCollector):
    """The Odds API 이벤트에서 경기 목록을 만든다.

    부상/라인업은 The Odds API가 제공하지 않으므로 빈 리스트(결측)로 둔다.
    (정형 통계는 별도 통계 API 필요 — 현재는 mock FeatureCollector가 담당.)

    The Odds API는 '다가오는 경기'를 며칠치 한꺼번에 주므로, target_date 단일
    날짜가 아니라 [target_date, target_date+window] 윈도우로 받는다(라이브에선
    오늘 경기가 0건이어도 향후 발매 경기를 분석할 수 있게).
    """

    def __init__(self, client: OddsApiClient, window_days: int = 3) -> None:
        self._client = client
        self._window_days = window_days

    def collect_matches(self, sport: Sport, target_date: date) -> list[Match]:
        matches: list[Match] = []
        for ev in self._client.events_for_sport(sport):
            try:
                m = parse_event_to_match(ev, sport)
            except (KeyError, ValueError):
                continue
            delta = (m.start_time.date() - target_date).days
            if 0 <= delta <= self._window_days:
                matches.append(m)
        return matches

    def collect_injuries(self, match: Match) -> list[InjuryNote]:
        return []  # The Odds API 미제공

    def collect_lineups(self, match: Match) -> list[Lineup]:
        return []  # The Odds API 미제공


class OddsApiOddsCollector(OddsCollector):
    """캐시된 이벤트에서 경기별 배당을 추출(추가 쿼터 소모 없음)."""

    def __init__(self, client: OddsApiClient) -> None:
        self._client = client

    def collect_odds(self, match: Match) -> list[OddsQuote]:
        for ev in self._client.events_for_sport(match.sport):
            if ev.get("id") == match.id:
                return parse_event_to_quotes(ev, match.sport)
        return []
