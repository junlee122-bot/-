"""수집 파이프라인.

4개의 수집기를 주입받아, 종목/날짜별로 경기를 모으고 각 경기에 배당·부상·
뉴스를 붙여 종목 공통 포맷(NormalizedMatchBundle) 리스트로 정규화한다.

베트맨에 발매되지 않은 경기는 분석/베팅 대상이 아니므로 기본적으로 제외한다.
"""

from __future__ import annotations

from datetime import date

from ..domain.enums import Sport
from ..domain.models import CollectionRequest, NormalizedMatchBundle
from .base import (
    BetmanCollector,
    FeatureCollector,
    MatchCollector,
    NewsCollector,
    OddsCollector,
)


class DataCollectionPipeline:
    def __init__(
        self,
        match_collector: MatchCollector,
        odds_collector: OddsCollector,
        betman_collector: BetmanCollector,
        news_collector: NewsCollector,
        feature_collector: FeatureCollector | None = None,
        *,
        require_betman: bool = True,
    ) -> None:
        self._matches = match_collector
        self._odds = odds_collector
        self._betman = betman_collector
        self._news = news_collector
        self._features = feature_collector
        # True면 베트맨 미발매 경기는 제외 (실제 베팅 대상만 남김)
        self._require_betman = require_betman

    def run(self, request: CollectionRequest) -> list[NormalizedMatchBundle]:
        bundles: list[NormalizedMatchBundle] = []
        for sport in request.sports:
            bundles.extend(self._collect_sport(sport, request.target_date))
        return bundles

    def _collect_sport(
        self, sport: Sport, target_date: date
    ) -> list[NormalizedMatchBundle]:
        out: list[NormalizedMatchBundle] = []
        for match in self._matches.collect_matches(sport, target_date):
            betman = self._betman.collect_offerings(match)
            if self._require_betman and not any(o.sales_open for o in betman):
                # 베트맨에 발매 안 된 경기는 참고 정보일 뿐 → 건너뜀
                continue

            bundle = NormalizedMatchBundle(
                match=match,
                betman_offerings=betman,
                overseas_odds=self._odds.collect_odds(match),
                injuries=self._matches.collect_injuries(match),
                lineups=self._matches.collect_lineups(match),
                news=self._news.collect_news(match),
                features=(
                    self._features.collect_features(match)
                    if self._features is not None
                    else None
                ),
            )
            out.append(bundle)
        return out


def summarize_bundles(bundles: list[NormalizedMatchBundle]) -> str:
    """수집 결과를 사람이 읽을 수 있게 요약 (데모/디버그용)."""
    if not bundles:
        return "수집된 경기가 없습니다."

    by_sport: dict[Sport, int] = {}
    for b in bundles:
        by_sport[b.match.sport] = by_sport.get(b.match.sport, 0) + 1

    lines = [f"총 {len(bundles)}경기 수집 (베트맨 발매 경기 기준)", ""]
    for sport, count in sorted(by_sport.items(), key=lambda kv: kv[0].value):
        lines.append(f"  · {sport.value:<11} {count}경기")
    lines.append("")

    for b in bundles:
        m = b.match
        lines.append(
            f"[{m.sport.value}] {m.home.name} vs {m.away.name}  ({m.league})"
        )
        feat_str = ""
        if b.features is not None:
            from ..domain.features import completeness

            feat_str = f" | feature 충실도 {completeness(b.features):.0%}"
        lines.append(
            f"    베트맨 발매 {len(b.betman_offerings)}항목 | "
            f"해외 북메이커 {b.overseas_bookmaker_count}곳 "
            f"({len(b.overseas_odds)}배당) | "
            f"부상 {len(b.injuries)} | 뉴스 {len(b.news)}건{feat_str}"
        )
    return "\n".join(lines)
