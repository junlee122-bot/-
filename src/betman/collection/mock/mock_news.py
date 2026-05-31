"""mock NewsCollector — 비정형 뉴스/분석글 원문 생성.

여기서는 LLM 처리 전 '원문'만 만든다. 요약·감성분류(SentimentFlag화)는
3단계 분석 레이어의 LLM이 담당한다.
"""

from __future__ import annotations

import random
from datetime import timedelta

from ...domain.models import Match, NewsItem
from ..base import NewsCollector
from ._fixtures import seed_from

_TEMPLATES = [
    ("{team} 주전 복귀 임박, 전력 상승 기대", "{team}의 핵심 선수가 부상에서 회복해 이번 경기 출전이 유력하다."),
    ("{team} 최근 분위기 저조… 연패 끊을까", "{team}는 최근 경기력이 떨어지며 팬들의 우려가 커지고 있다."),
    ("{team} 감독 '홈에서 반드시 승리'", "{team} 감독은 기자회견에서 자신감을 드러냈다."),
    ("{team} 원정 약세 지속되나", "{team}는 원정 성적이 부진해 이번 경기도 쉽지 않을 전망이다."),
    ("전문가 분석: {match} 박빙 예상", "양 팀 전력이 비슷해 결과를 예측하기 어렵다는 분석이 나온다."),
]

_SOURCES = ["sports_news_api", "league_feed", "analyst_blog_feed"]


class MockNewsCollector(NewsCollector):
    def collect_news(self, match: Match) -> list[NewsItem]:
        rng = random.Random(seed_from(match.id, "news"))
        n = rng.randint(1, 4)
        match_label = f"{match.home.name} vs {match.away.name}"

        items: list[NewsItem] = []
        for _ in range(n):
            title_t, body_t = rng.choice(_TEMPLATES)
            team = rng.choice([match.home.name, match.away.name])
            items.append(
                NewsItem(
                    source=rng.choice(_SOURCES),
                    title=title_t.format(team=team, match=match_label),
                    body=body_t.format(team=team, match=match_label),
                    published_at=match.start_time - timedelta(hours=rng.randint(1, 48)),
                    url=f"https://example.feed/{match.id}/{rng.randint(1000, 9999)}",
                )
            )
        return items
