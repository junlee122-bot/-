"""mock MatchCollector — 경기 일정/부상/라인업 생성."""

from __future__ import annotations

import random
from datetime import date, datetime, time

from ...domain.enums import MatchStatus, Sport
from ...domain.models import InjuryNote, Lineup, Match, Team
from ..base import MatchCollector
from ._fixtures import LEAGUES, seed_from


class MockMatchCollector(MatchCollector):
    """종목별로 2~3경기를 결정론적으로 생성한다."""

    def collect_matches(self, sport: Sport, target_date: date) -> list[Match]:
        league, teams = LEAGUES[sport]
        rng = random.Random(seed_from(sport.value, target_date.isoformat()))

        n_matches = rng.randint(2, 3)
        pool = teams[:]
        rng.shuffle(pool)

        matches: list[Match] = []
        for i in range(n_matches):
            if len(pool) < 2:
                break
            home_name, away_name = pool.pop(), pool.pop()
            kickoff = datetime.combine(target_date, time(hour=18 + i, minute=0))
            match_id = f"{sport.value}-{target_date.isoformat()}-{i}"
            matches.append(
                Match(
                    id=match_id,
                    sport=sport,
                    league=league,
                    home=Team(id=f"{sport.value}-{home_name}", name=home_name, sport=sport),
                    away=Team(id=f"{sport.value}-{away_name}", name=away_name, sport=sport),
                    start_time=kickoff,
                    status=MatchStatus.SCHEDULED,
                )
            )
        return matches

    def collect_injuries(self, match: Match) -> list[InjuryNote]:
        rng = random.Random(seed_from(match.id, "injury"))
        notes: list[InjuryNote] = []
        for team in (match.home, match.away):
            for _ in range(rng.randint(0, 2)):
                status = rng.choice(["out", "doubtful", "questionable"])
                notes.append(
                    InjuryNote(
                        team_id=team.id,
                        player_name=f"{team.name} 선수{rng.randint(1, 30)}",
                        status=status,
                        note=rng.choice(
                            ["햄스트링", "발목 염좌", "감기 몸살", "개인 사정", "출전 미정"]
                        ),
                    )
                )
        return notes

    def collect_lineups(self, match: Match) -> list[Lineup]:
        rng = random.Random(seed_from(match.id, "lineup"))
        lineups: list[Lineup] = []
        for team in (match.home, match.away):
            confirmed = rng.random() > 0.5
            lineups.append(
                Lineup(
                    team_id=team.id,
                    confirmed=confirmed,
                    players=tuple(f"{team.name} 선수{n}" for n in range(1, 6)),
                )
            )
        return lineups
