"""mock FeatureCollector — 종목별 예측 변수 생성.

결측치를 실제처럼 모사한다: 일부 항목은 Feature.missing 으로 채워, 결측을
0으로 뭉개지 않고 명시적으로 표현하는 파이프라인을 검증한다.
유료 통계/배당 API 구현으로 교체할 때 이 파일만 갈아끼우면 된다.
"""

from __future__ import annotations

import random
from datetime import timedelta

from ...domain.enums import Outcome, Sport
from ...domain.features import (
    BaseballMatchFeatures,
    BaseballTeamFeatures,
    BasketballMatchFeatures,
    BasketballTeamFeatures,
    CommonMatchFeatures,
    CommonTeamFeatures,
    Feature,
    HeadToHead,
    InjuryImpact,
    LineMovement,
    LineMovementPoint,
    MatchFeatures,
    PitcherStats,
    RecordSplit,
    SoccerMatchFeatures,
    SoccerTeamFeatures,
    TeamFeatures,
    Weather,
)
from ...domain.models import Match, Team
from ..base import FeatureCollector
from ._fixtures import seed_from

# 결측 확률: 항목마다 이 확률로 Feature.missing 처리
_MISSING_P = 0.12


def _maybe(rng: random.Random, name: str, value, *, source: str):
    """확률적으로 결측 처리하는 헬퍼."""
    if rng.random() < _MISSING_P:
        return Feature.missing(name, source=source)
    return Feature.known(name, value, source=source)


def _record(rng: random.Random, games: int, has_draw: bool) -> RecordSplit:
    wins = rng.randint(0, games)
    draws = rng.randint(0, games - wins) if has_draw else 0
    losses = games - wins - draws
    scored = round(rng.uniform(0.8, 3.2) * games, 1)
    conceded = round(rng.uniform(0.8, 3.2) * games, 1)
    return RecordSplit(games, wins, draws, losses, scored, conceded)


class MockFeatureCollector(FeatureCollector):
    def collect_features(self, match: Match) -> MatchFeatures:
        sport = match.sport
        return MatchFeatures(
            match_id=match.id,
            sport=sport,
            home=self._team(match, match.home, "home"),
            away=self._team(match, match.away, "away"),
            common_match=self._common_match(match),
            soccer=self._soccer_match(match) if sport == Sport.SOCCER else None,
            baseball=self._baseball_match(match) if sport == Sport.BASEBALL else None,
            basketball=(
                self._basketball_match(match) if sport == Sport.BASKETBALL else None
            ),
        )

    # ---------------- 팀 단위 ---------------- #
    def _team(self, match: Match, team: Team, side: str) -> TeamFeatures:
        rng = random.Random(seed_from(match.id, "feat", side))
        has_draw = match.sport.has_draw
        src = "stats_api_mock"

        common = CommonTeamFeatures(
            recent_form_overall=_maybe(
                rng, "recent_form_overall", _record(rng, 10, has_draw), source=src
            ),
            recent_form_home=_maybe(
                rng, "recent_form_home", _record(rng, 5, has_draw), source=src
            ),
            recent_form_away=_maybe(
                rng, "recent_form_away", _record(rng, 5, has_draw), source=src
            ),
            rest_days=_maybe(rng, "rest_days", rng.randint(0, 6), source=src),
            games_last_7d=_maybe(rng, "games_last_7d", rng.randint(1, 4), source=src),
            is_back_to_back=_maybe(
                rng, "is_back_to_back", rng.random() < 0.25, source=src
            ),
            travel_km=_maybe(
                rng, "travel_km", round(rng.uniform(0, 8000), 0), source=src
            ),
            timezone_shift_hours=_maybe(
                rng, "timezone_shift_hours", rng.randint(0, 9), source=src
            ),
            league_rank=_maybe(rng, "league_rank", rng.randint(1, 12), source=src),
            games_remaining=_maybe(
                rng, "games_remaining", rng.randint(0, 30), source=src
            ),
            injuries=_maybe(
                rng, "injuries", self._injuries(rng, team), source="news+stats_mock"
            ),
        )

        soccer = baseball = basketball = None
        if match.sport == Sport.SOCCER:
            soccer = self._soccer_team(rng, team)
        elif match.sport == Sport.BASEBALL:
            baseball = self._baseball_team(rng, team)
        elif match.sport == Sport.BASKETBALL:
            basketball = self._basketball_team(rng, team)

        return TeamFeatures(team.id, side, common, soccer, baseball, basketball)

    def _injuries(self, rng: random.Random, team: Team) -> tuple[InjuryImpact, ...]:
        out = []
        for _ in range(rng.randint(0, 2)):
            out.append(
                InjuryImpact(
                    player_name=f"{team.name} 선수{rng.randint(1, 30)}",
                    status=rng.choice(["out", "doubtful", "suspended"]),
                    contribution_share=round(rng.uniform(0.05, 0.4), 2),
                    role=rng.choice(["주전 공격수", "주전 수비수", "에이스", "주전 GK", "식스맨"]),
                )
            )
        return tuple(out)

    # ---------------- 축구 ---------------- #
    def _soccer_team(self, rng: random.Random, team: Team) -> SoccerTeamFeatures:
        src = "opta_mock"
        return SoccerTeamFeatures(
            xg_for=_maybe(rng, "xg_for", round(rng.uniform(0.6, 2.6), 2), source=src),
            xg_against=_maybe(
                rng, "xg_against", round(rng.uniform(0.6, 2.6), 2), source=src
            ),
            shots=_maybe(rng, "shots", round(rng.uniform(6, 20), 1), source=src),
            shots_on_target=_maybe(
                rng, "shots_on_target", round(rng.uniform(2, 9), 1), source=src
            ),
            set_piece_share=_maybe(
                rng, "set_piece_share", round(rng.uniform(0.1, 0.45), 2), source=src
            ),
            possession_adj_rating=_maybe(
                rng, "possession_adj_rating", round(rng.uniform(0.8, 1.3), 2), source=src
            ),
            confirmed_lineup=_maybe(
                rng, "confirmed_lineup", rng.random() > 0.5, source="lineup_feed_mock"
            ),
            key_absences=_maybe(
                rng,
                "key_absences",
                tuple(
                    f"{team.name} {r}"
                    for r in rng.sample(["공격수A", "수비수B", "GK"], rng.randint(0, 2))
                ),
                source="lineup_feed_mock",
            ),
        )

    def _soccer_match(self, match: Match) -> SoccerMatchFeatures:
        rng = random.Random(seed_from(match.id, "soccer-match"))
        src = "stats_api_mock"
        return SoccerMatchFeatures(
            draw_tendency=_maybe(
                rng, "draw_tendency", round(rng.uniform(0.22, 0.34), 2), source=src
            ),
            referee_card_rate=_maybe(
                rng, "referee_card_rate", round(rng.uniform(3.0, 6.5), 1), source=src
            ),
            referee_pen_rate=_maybe(
                rng, "referee_pen_rate", round(rng.uniform(0.1, 0.5), 2), source=src
            ),
            weather=_maybe(
                rng,
                "weather",
                Weather("rain" if rng.random() < 0.3 else "clear",
                        round(rng.uniform(2, 28), 1),
                        round(rng.uniform(0, 35), 1)),
                source="weather_api_mock",
            ),
            league_scoring_env=_maybe(
                rng, "league_scoring_env", round(rng.uniform(0.85, 1.2), 2), source=src
            ),
        )

    # ---------------- 야구 ---------------- #
    def _baseball_team(self, rng: random.Random, team: Team) -> BaseballTeamFeatures:
        src = "stats_api_mock"
        throws = rng.choice(["L", "R"])
        pitcher = PitcherStats(
            name=f"{team.name} 선발{rng.randint(1, 5)}",
            throws=throws,
            era=round(rng.uniform(2.5, 5.5), 2),
            fip=round(rng.uniform(2.8, 5.2), 2),
            whip=round(rng.uniform(1.0, 1.6), 2),
            recent_ip=round(rng.uniform(4.0, 7.0), 1),
            vs_opponent_note=rng.choice(["상대 강세", "상대 약세", "표본 적음"]),
        )
        return BaseballTeamFeatures(
            starting_pitcher=_maybe(
                rng, "starting_pitcher", pitcher, source="probable_pitcher_feed_mock"
            ),
            bullpen_fatigue=_maybe(
                rng, "bullpen_fatigue", round(rng.uniform(0.0, 1.0), 2), source=src
            ),
            lineup_vs_lhp=_maybe(
                rng, "lineup_vs_lhp", round(rng.uniform(0.6, 0.9), 3), source=src
            ),
            lineup_vs_rhp=_maybe(
                rng, "lineup_vs_rhp", round(rng.uniform(0.6, 0.9), 3), source=src
            ),
        )

    def _baseball_match(self, match: Match) -> BaseballMatchFeatures:
        rng = random.Random(seed_from(match.id, "baseball-match"))
        return BaseballMatchFeatures(
            park_factor=_maybe(
                rng, "park_factor", round(rng.uniform(0.92, 1.12), 2),
                source="stats_api_mock",
            ),
            weather=_maybe(
                rng,
                "weather",
                Weather("clear", round(rng.uniform(5, 30), 1),
                        round(rng.uniform(0, 25), 1),
                        wind_dir=rng.choice(["out", "in", "cross"])),
                source="weather_api_mock",
            ),
            is_doubleheader=_maybe(
                rng, "is_doubleheader", rng.random() < 0.1, source="schedule_mock"
            ),
            is_day_game=_maybe(
                rng, "is_day_game", rng.random() < 0.3, source="schedule_mock"
            ),
        )

    # ---------------- 농구 ---------------- #
    def _basketball_team(self, rng: random.Random, team: Team) -> BasketballTeamFeatures:
        src = "stats_api_mock"
        star_out = tuple(
            InjuryImpact(
                player_name=f"{team.name} 스타{i}",
                status=rng.choice(["out", "doubtful"]),
                contribution_share=round(rng.uniform(0.25, 0.5), 2),
                role="스타 선수",
            )
            for i in range(rng.randint(0, 1))
        )
        return BasketballTeamFeatures(
            pace=_maybe(rng, "pace", round(rng.uniform(92, 105), 1), source=src),
            offensive_rating=_maybe(
                rng, "offensive_rating", round(rng.uniform(105, 120), 1), source=src
            ),
            defensive_rating=_maybe(
                rng, "defensive_rating", round(rng.uniform(105, 120), 1), source=src
            ),
            star_absences=_maybe(
                rng, "star_absences", star_out, source="news+injury_report_mock"
            ),
            star_onoff=_maybe(
                rng, "star_onoff", round(rng.uniform(2.0, 12.0), 1), source=src
            ),
        )

    def _basketball_match(self, match: Match) -> BasketballMatchFeatures:
        rng = random.Random(seed_from(match.id, "basketball-match"))
        return BasketballMatchFeatures(
            matchup_mismatch=_maybe(
                rng,
                "matchup_mismatch",
                rng.choice(["리바운드 우위(홈)", "페이스 미스매치", "특이사항 없음"]),
                source="stats_api_mock",
            ),
            home_court_factor=_maybe(
                rng, "home_court_factor", round(rng.uniform(1.5, 4.0), 1),
                source="stats_api_mock",
            ),
        )

    # ---------------- 공통 경기 ---------------- #
    def _common_match(self, match: Match) -> CommonMatchFeatures:
        rng = random.Random(seed_from(match.id, "common-match"))
        has_draw = match.sport.has_draw
        meetings = rng.randint(3, 10)
        hw = rng.randint(0, meetings)
        dw = rng.randint(0, meetings - hw) if has_draw else 0
        aw = meetings - hw - dw
        results = ["H"] * hw + ["D"] * dw + ["A"] * aw
        rng.shuffle(results)

        movements = self._line_movements(match, rng)

        return CommonMatchFeatures(
            head_to_head=_maybe(
                rng,
                "head_to_head",
                HeadToHead(meetings, hw, dw, aw, tuple(results[:5])),
                source="stats_api_mock",
            ),
            line_movement=_maybe(
                rng, "line_movement", movements, source="odds_api_mock"
            ),
            is_derby=_maybe(rng, "is_derby", rng.random() < 0.15, source="stats_api_mock"),
            motivation_note=_maybe(
                rng,
                "motivation_note",
                rng.choice(["상위권 다툼", "잔류 경쟁", "소화전 성격", "더비 분위기"]),
                source="editorial_mock",
            ),
        )

    def _line_movements(
        self, match: Match, rng: random.Random
    ) -> tuple[LineMovement, ...]:
        outcomes = (
            [Outcome.HOME, Outcome.DRAW, Outcome.AWAY]
            if match.sport.has_draw
            else [Outcome.HOME, Outcome.AWAY]
        )
        out = []
        for oc in outcomes:
            open_odds = round(rng.uniform(1.5, 3.5), 2)
            drift = rng.uniform(-0.4, 0.4)
            current = round(max(1.05, open_odds + drift), 2)
            pts = tuple(
                LineMovementPoint(
                    match.start_time - timedelta(hours=h),
                    round(open_odds + drift * (1 - h / 48), 2),
                )
                for h in (48, 24, 6, 1)
            )
            out.append(LineMovement(oc, open_odds, current, pts))
        return tuple(out)
