"""예측 변수(feature) 스키마.

세 종목(축구/야구/농구, 해외 포함)에서 예측력이 있는 정보를 종목 공통/종목별로
정규화한다. 설계 원칙:

1) 모든 예측 변수는 `Feature[T]` 로 감싼다.
   - 항목마다 개별 이름을 가지므로 value 점수 모델에서 **가중치를 따로** 둘 수 있다.
   - `present=False` 로 **결측치를 명시적으로** 표현한다 (값을 0으로 뭉개지 않는다).
   - source/as_of/note 로 출처·기준시각·비고를 남긴다 (사후 검증용).

2) 종목마다 '가장 결정적인 변수'가 다르다.
   - 축구: xG / 확정 라인업
   - 야구: 선발투수 매치업
   - 농구: 휴식(백투백) / 스타 결장
   이 우선순위는 analysis/weights.py 의 종목별 가중치에 반영된다.
"""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from datetime import datetime
from typing import Generic, Iterator, Optional, TypeVar

from .enums import Outcome, Sport

T = TypeVar("T")


# --------------------------------------------------------------------------- #
# 결측치를 명시하는 범용 래퍼
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Feature(Generic[T]):
    """하나의 예측 변수. 가중치는 외부(weights.py)에서 이름으로 부여한다."""

    name: str
    value: Optional[T] = None
    present: bool = False          # False = 결측치 (명시적)
    source: str = ""
    as_of: Optional[datetime] = None
    note: str = ""

    @classmethod
    def known(
        cls,
        name: str,
        value: T,
        *,
        source: str = "",
        as_of: Optional[datetime] = None,
        note: str = "",
    ) -> "Feature[T]":
        return cls(name, value, True, source, as_of, note)

    @classmethod
    def missing(cls, name: str, *, source: str = "", note: str = "데이터 없음") -> "Feature[T]":
        return cls(name, None, False, source, None, note)

    def __bool__(self) -> bool:  # 존재 여부로 truthiness 판단
        return self.present


# --------------------------------------------------------------------------- #
# 공통 보조 구조
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class RecordSplit:
    """특정 구간(예: 최근 10경기)의 성적 + 득실."""

    games: int
    wins: int
    draws: int
    losses: int
    scored: float        # 득점(축구·농구) / 득점(야구)
    conceded: float      # 실점

    @property
    def ppg(self) -> float:
        """경기당 승점 (승3·무1)."""
        return (self.wins * 3 + self.draws) / self.games if self.games else 0.0

    @property
    def diff_per_game(self) -> float:
        return (self.scored - self.conceded) / self.games if self.games else 0.0

    @property
    def win_rate(self) -> float:
        return self.wins / self.games if self.games else 0.0


@dataclass(frozen=True)
class HeadToHead:
    """맞대결 전적(최근 위주)."""

    meetings: int
    home_wins: int
    draws: int
    away_wins: int
    recent_results: tuple[str, ...] = ()   # 예: ("H", "D", "A", "H")


@dataclass(frozen=True)
class LineMovementPoint:
    captured_at: datetime
    decimal_odds: float


@dataclass(frozen=True)
class LineMovement:
    """해외 배당의 시간대별 변동(라인 무브먼트) — 한 선택지 기준."""

    outcome: Outcome
    open_odds: float
    current_odds: float
    points: tuple[LineMovementPoint, ...] = ()

    @property
    def drift(self) -> float:
        """양수면 배당이 길어짐(확률 하락), 음수면 짧아짐(시장이 쏠림)."""
        return self.current_odds - self.open_odds


@dataclass(frozen=True)
class InjuryImpact:
    """결장/부상/징계 + 그 선수의 팀 기여도."""

    player_name: str
    status: str                  # out / doubtful / suspended ...
    contribution_share: float    # 0.0~1.0, 팀 기여도(=결장 시 타격 크기)
    role: str = ""               # 예: 주전 공격수, 에이스, 주전 GK


@dataclass(frozen=True)
class Weather:
    condition: str               # clear / rain / wind ...
    temp_c: float
    wind_kph: float
    wind_dir: str = ""           # 야구 바람 방향에 중요
    precipitation_mm: float = 0.0


@dataclass(frozen=True)
class PitcherStats:
    """야구 선발투수."""

    name: str
    throws: str                  # "L" / "R"
    era: float
    fip: float
    whip: float
    recent_ip: float             # 최근 등판 이닝(부하 가늠)
    vs_opponent_note: str = ""   # 상대 타선과의 과거 상대 전적 요약


# --------------------------------------------------------------------------- #
# 공통 feature 그룹 (세 종목)
# --------------------------------------------------------------------------- #
@dataclass
class CommonTeamFeatures:
    """팀 단위 공통 변수 (홈/원정 각각 생성)."""

    recent_form_overall: Feature[RecordSplit]
    recent_form_home: Feature[RecordSplit]
    recent_form_away: Feature[RecordSplit]
    rest_days: Feature[int]                  # 직전 경기와의 간격
    games_last_7d: Feature[int]              # 연전 강도
    is_back_to_back: Feature[bool]           # 이틀 연속 경기
    travel_km: Feature[float]                # 이동 거리(해외 원정)
    timezone_shift_hours: Feature[int]       # 시차
    league_rank: Feature[int]                # 리그 순위(동기)
    games_remaining: Feature[int]            # 잔여 일정(동기)
    injuries: Feature[tuple[InjuryImpact, ...]]  # 결장/부상/징계 + 기여도


@dataclass
class CommonMatchFeatures:
    """경기 단위 공통 변수."""

    head_to_head: Feature[HeadToHead]
    line_movement: Feature[tuple[LineMovement, ...]]   # 선택지별 무브먼트
    is_derby: Feature[bool]                            # 더비/라이벌전
    motivation_note: Feature[str]                      # 잔여일정 중요도 등 요약


# --------------------------------------------------------------------------- #
# 축구 — 핵심: xG + 확정 라인업
# --------------------------------------------------------------------------- #
@dataclass
class SoccerTeamFeatures:
    xg_for: Feature[float]                 # 기대득점 (핵심)
    xg_against: Feature[float]             # 피기대득점 (핵심)
    shots: Feature[float]
    shots_on_target: Feature[float]
    set_piece_share: Feature[float]        # 세트피스 득점 비중
    possession_adj_rating: Feature[float]  # 점유율 보정 지표
    confirmed_lineup: Feature[bool]        # 확정 라인업 여부 (핵심)
    key_absences: Feature[tuple[str, ...]] # 핵심 공격수/수비수/GK 결장


@dataclass
class SoccerMatchFeatures:
    draw_tendency: Feature[float]          # 무승부 경향(무 확률 별도 추정)
    referee_card_rate: Feature[float]      # 심판 카드 성향
    referee_pen_rate: Feature[float]       # 심판 페널티 성향
    weather: Feature[Weather]
    league_scoring_env: Feature[float]     # 리그별 득점 환경 정규화 계수


# --------------------------------------------------------------------------- #
# 야구 — 핵심: 선발투수 매치업
# --------------------------------------------------------------------------- #
@dataclass
class BaseballTeamFeatures:
    starting_pitcher: Feature[PitcherStats]   # 선발투수 (핵심)
    bullpen_fatigue: Feature[float]           # 불펜 누적 피로도(최근 등판)
    lineup_vs_lhp: Feature[float]             # 좌투 상대 타선 스플릿(OPS 등)
    lineup_vs_rhp: Feature[float]             # 우투 상대 타선 스플릿


@dataclass
class BaseballMatchFeatures:
    park_factor: Feature[float]               # 구장 팩터
    weather: Feature[Weather]                 # 특히 바람
    is_doubleheader: Feature[bool]
    is_day_game: Feature[bool]


# --------------------------------------------------------------------------- #
# 농구 — 핵심: 휴식 / 스타 결장
# --------------------------------------------------------------------------- #
@dataclass
class BasketballTeamFeatures:
    pace: Feature[float]                       # 경기 속도
    offensive_rating: Feature[float]
    defensive_rating: Feature[float]
    star_absences: Feature[tuple[InjuryImpact, ...]]  # 스타 결장 (핵심)
    star_onoff: Feature[float]                # 스타 온/오프 영향력


@dataclass
class BasketballMatchFeatures:
    matchup_mismatch: Feature[str]            # 페이스/리바운드 미스매치 요약
    home_court_factor: Feature[float]         # 홈코트 이점


# --------------------------------------------------------------------------- #
# 한 경기의 모든 feature 묶음
# --------------------------------------------------------------------------- #
@dataclass
class TeamFeatures:
    team_id: str
    side: str                                  # "home" / "away"
    common: CommonTeamFeatures
    soccer: Optional[SoccerTeamFeatures] = None
    baseball: Optional[BaseballTeamFeatures] = None
    basketball: Optional[BasketballTeamFeatures] = None


@dataclass
class MatchFeatures:
    match_id: str
    sport: Sport
    home: TeamFeatures
    away: TeamFeatures
    common_match: CommonMatchFeatures
    soccer: Optional[SoccerMatchFeatures] = None
    baseball: Optional[BaseballMatchFeatures] = None
    basketball: Optional[BasketballMatchFeatures] = None


# --------------------------------------------------------------------------- #
# feature 평탄화 — 이름→Feature 매핑 (가중치 부여/로깅에 사용)
# --------------------------------------------------------------------------- #
def iter_features(obj: object, prefix: str = "") -> Iterator[tuple[str, Feature]]:
    """중첩 dataclass를 재귀적으로 훑어 (점-구분 이름, Feature)를 산출한다.

    예: "home.common.rest_days", "home.soccer.xg_for", "match.draw_tendency"
    """
    if obj is None:
        return
    if isinstance(obj, Feature):
        yield prefix.rstrip("."), obj
        return
    if is_dataclass(obj):
        for f in fields(obj):
            child = getattr(obj, f.name)
            yield from iter_features(child, f"{prefix}{f.name}.")


def flatten_features(mf: MatchFeatures) -> dict[str, Feature]:
    """MatchFeatures 전체를 이름→Feature 평면 딕셔너리로."""
    flat: dict[str, Feature] = {}
    for side_name, side in (("home", mf.home), ("away", mf.away)):
        for sub in (side.common, side.soccer, side.baseball, side.basketball):
            for name, feat in iter_features(sub):
                if name:
                    flat[f"{side_name}.{name}"] = feat
    for sub in (mf.common_match, mf.soccer, mf.baseball, mf.basketball):
        for name, feat in iter_features(sub):
            if name:
                flat[f"match.{name}"] = feat
    return flat


def completeness(mf: MatchFeatures) -> float:
    """수집된 feature 중 결측이 아닌 비율 (데이터 신뢰도 가늠)."""
    flat = flatten_features(mf)
    if not flat:
        return 0.0
    present = sum(1 for f in flat.values() if f.present)
    return present / len(flat)
