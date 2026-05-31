"""종목별 feature 가중치 레지스트리.

핵심 설계 요구사항 두 가지를 만족한다:
  1) 항목마다 예측 가중치를 '따로' 둘 수 있다 (feature 이름 → 가중치).
  2) value 점수 모델을 종목별로 분리한다 (종목마다 결정적 변수가 다름).

여기 값은 '초기 캘리브레이션 전' 사전(prior) 가중치다. 3단계에서 과거 데이터로
백테스트해 갱신한다. 가중치는 home./away. 접두어를 떼고 base 이름으로 매칭한다.

종목별 '핵심 변수'에 가장 큰 가중치를 둔다:
  · 축구  → xg_for / xg_against / confirmed_lineup / key_absences
  · 야구  → starting_pitcher / bullpen_fatigue
  · 농구  → is_back_to_back / star_absences / rest_days
"""

from __future__ import annotations

from ..domain.enums import Sport

# 모든 종목 공통 변수의 사전 가중치 (base 이름 기준)
_COMMON: dict[str, float] = {
    "common.recent_form_overall": 1.0,
    "common.recent_form_home": 0.8,
    "common.recent_form_away": 0.8,
    "common.rest_days": 0.5,
    "common.games_last_7d": 0.4,
    "common.is_back_to_back": 0.5,
    "common.travel_km": 0.3,
    "common.timezone_shift_hours": 0.3,
    "common.league_rank": 0.6,
    "common.games_remaining": 0.3,
    "common.injuries": 0.9,
    "head_to_head": 0.5,
    "line_movement": 1.2,          # 시장 신호는 강한 사전 가중치
    "is_derby": 0.3,
    "motivation_note": 0.3,
}

# 종목별 핵심 변수 가중치 (공통 위에 덮어쓰기/추가)
_SPORT: dict[Sport, dict[str, float]] = {
    Sport.SOCCER: {
        "soccer.xg_for": 2.0,                 # 핵심
        "soccer.xg_against": 2.0,             # 핵심
        "soccer.confirmed_lineup": 1.5,       # 핵심
        "soccer.key_absences": 1.5,           # 핵심
        "soccer.shots": 0.6,
        "soccer.shots_on_target": 0.8,
        "soccer.set_piece_share": 0.5,
        "soccer.possession_adj_rating": 0.7,
        "draw_tendency": 1.0,                 # 무 확률 별도 추정
        "referee_card_rate": 0.2,
        "referee_pen_rate": 0.2,
        "weather": 0.3,
        "league_scoring_env": 0.6,            # 리그 간 득점환경 정규화
    },
    Sport.BASEBALL: {
        "baseball.starting_pitcher": 2.2,     # 핵심
        "baseball.bullpen_fatigue": 1.0,
        "baseball.lineup_vs_lhp": 0.8,
        "baseball.lineup_vs_rhp": 0.8,
        "park_factor": 0.6,
        "weather": 0.5,                       # 바람
        "is_doubleheader": 0.3,
        "is_day_game": 0.2,
    },
    Sport.BASKETBALL: {
        "basketball.star_absences": 2.0,      # 핵심
        "basketball.star_onoff": 1.2,
        "basketball.offensive_rating": 1.0,
        "basketball.defensive_rating": 1.0,
        "basketball.pace": 0.6,
        "matchup_mismatch": 0.6,
        "home_court_factor": 0.7,
        # 농구는 휴식/백투백이 핵심 → 공통값을 상향
        "common.is_back_to_back": 1.5,
        "common.rest_days": 1.2,
    },
}


def _base_name(feature_name: str) -> str:
    """'home.common.rest_days' → 'common.rest_days', 'match.weather' → 'weather'."""
    if feature_name.startswith(("home.", "away.")):
        return feature_name.split(".", 1)[1]
    if feature_name.startswith("match."):
        return feature_name.split(".", 1)[1]
    return feature_name


def weight_for(sport: Sport, feature_name: str) -> float:
    """주어진 종목에서 feature의 사전 가중치. 미등록 항목은 0.0."""
    base = _base_name(feature_name)
    sport_table = _SPORT.get(sport, {})
    if base in sport_table:
        return sport_table[base]
    return _COMMON.get(base, 0.0)


def active_weights(sport: Sport) -> dict[str, float]:
    """해당 종목에서 0이 아닌 모든 (base 이름 → 가중치)."""
    merged = dict(_COMMON)
    merged.update(_SPORT.get(sport, {}))
    return {k: v for k, v in merged.items() if v != 0.0}
