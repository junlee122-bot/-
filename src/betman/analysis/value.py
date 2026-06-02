"""value 분석기 — 모든 신호를 종목별로 합쳐 픽을 줄 세운다.

파이프라인(프롬프트 요구 반영):
  1) Pinnacle 샤프 기준선 de-vig → 공정 확률(진짜 확률 기준)  [devig.py]
  2) 베트맨 고정배당 vs 공정 확률 → edge(%)와 EV(환급률 63% 반영)
  3) Elo 레이팅과 공정 확률을 블렌딩(신뢰도 가중)            [ratings.py]
  4) 평균회귀 신호(기대지표 좋은데 최근 결과 나쁜 팀)        [features]
  5) LLM/규칙 기반 비정형 플래그를 '보조 가중치로만' 반영    [sentiment.py]
  6) 종목별로 value 점수를 분리 계산·캘리브레이션

핵심 전제: 환급률 63% 때문에 EV는 대부분 음수. 이 도구는 '이기는 픽'이 아니라
'상대적으로 덜 불리한 픽'을 줄 세운다 (출력에 명시).
"""

from __future__ import annotations

from dataclasses import dataclass

from ..config import BETMAN_PAYOUT_RATE
from ..domain.enums import Outcome, Sport
from ..domain.features import MatchFeatures, completeness
from ..domain.models import NormalizedMatchBundle, SentimentFlag
from ..domain.enums import MarketType
from .base import PickAnalysis, SentimentClassifier, ValueAnalyzer
from .derived import (
    LEAGUE_TOTAL_HINT,
    handicap_probs,
    infer_goal_model,
    infer_goal_model_2way,
    match_1x2_probs,
    sum_oddeven_probs,
    totals_probs,
)
from .devig import ProportionalDevig, compute_fair_line
from .market import summarize_movements
from .ratings import EloBook, win_draw_loss_probs
from .sentiment import RuleBasedSentimentClassifier


# 종목별 value 점수 캘리브레이션 계수 (백테스트로 갱신 대상)
@dataclass(frozen=True)
class SportCalibration:
    edge_weight: float        # edge(%)를 value로 반영하는 비중
    signal_weight: float      # 비정형 플래그 보조 가중치 상한
    elo_blend: float          # 공정확률 vs Elo 블렌딩에서 Elo 비중(0~1)
    notable_threshold: float  # '주목 픽' 기준선(비핵심 종목 출력 필터)


_CALIB: dict[Sport, SportCalibration] = {
    # 축구: 무승부 3갈래 + 라인업 변수 큼 → 신호 가중치 약간 높임
    Sport.SOCCER: SportCalibration(1.0, 0.20, 0.30, 6.0),
    # 야구: 선발 매치업 지배적, 시장 효율 높음 → edge 신뢰
    Sport.BASEBALL: SportCalibration(1.0, 0.15, 0.20, 7.0),
    # 농구: 휴식/결장 뉴스 영향 큼 → 신호 가중치 높임
    Sport.BASKETBALL: SportCalibration(1.0, 0.25, 0.35, 6.0),
    Sport.VOLLEYBALL: SportCalibration(0.9, 0.15, 0.25, 8.0),
    Sport.HOCKEY: SportCalibration(0.9, 0.15, 0.25, 8.0),
    Sport.ESPORTS: SportCalibration(0.8, 0.20, 0.30, 8.0),
}


def calibration_for(sport: Sport) -> SportCalibration:
    return _CALIB.get(sport, SportCalibration(1.0, 0.15, 0.25, 8.0))


def _signal_adjustment(
    outcome: Outcome, flags: list[SentimentFlag], cap: float
) -> tuple[float, tuple[SentimentFlag, ...]]:
    """해당 선택지에 걸리는 비정형 플래그를 합산해 보조 조정값 산출.

    positive면 +, negative면 −. confidence로 가중. 합은 ±cap 으로 클램프.
    '보조 가중치로만' 반영하므로 영향은 제한적.
    """
    adj = 0.0
    used: list[SentimentFlag] = []
    for f in flags:
        if f.target_outcome != outcome:
            continue
        sign = 0.0
        if f.polarity.value == "positive":
            sign = 1.0
        elif f.polarity.value == "negative":
            sign = -1.0
        if sign:
            adj += sign * f.confidence
            used.append(f)
    adj = max(-1.0, min(1.0, adj)) * cap
    return adj, tuple(used)


def _mean_reversion_flag(
    features: MatchFeatures | None, side: str, sport: Sport
) -> bool:
    """기대 지표는 좋은데 최근 결과가 나쁜 팀 신호 (평균회귀 후보).

    축구는 xG로, 그 외는 최근 폼 득실 대비 승률 괴리로 근사.
    """
    if features is None:
        return False
    team = features.home if side == "home" else features.away

    if sport == Sport.SOCCER and team.soccer:
        xgf, xga = team.soccer.xg_for, team.soccer.xg_against
        form = team.common.recent_form_overall
        if xgf.present and xga.present and form.present:
            xg_diff = xgf.value - xga.value
            rec = form.value
            # 기대 득실차는 +인데 실제 승점은 낮음 → 평균회귀 상승 후보
            return xg_diff > 0.3 and rec.ppg < 1.2
        return False

    # 야구·농구 등: 득실차는 +인데 승률 낮음
    form = team.common.recent_form_overall
    if form.present:
        rec = form.value
        return rec.diff_per_game > 0.1 and rec.win_rate < 0.45
    return False


class DefaultValueAnalyzer(ValueAnalyzer):
    def __init__(
        self,
        classifier: SentimentClassifier | None = None,
        elo: EloBook | None = None,
    ) -> None:
        self._devig = ProportionalDevig()
        self._classifier = classifier or RuleBasedSentimentClassifier()
        self._elo = elo or EloBook()

    def _fair_for(self, off, fair, goal_model, sport) -> tuple[float, bool]:
        """발매 항목의 공정확률과 모델기반 여부를 반환.

        - 머니라인(2갈래): Pinnacle de-vig 직접 (model_based=False)
        - 1X2: 무승부 있는 종목(축구·하키)만 Pinnacle 직접. 야구 '승1패'처럼
          무승부가 드문 종목의 3갈래는 Pinnacle 이 무 확률을 안 줘서 직접 비교가
          불가 → 포아송 모델로 정시(9이닝) 무/승/패 추정(model_based=True).
        - 핸디캡/언오버/SUM: 포아송 모델 추정.
        모델이 없거나 평가 불가하면 0 반환 → 호출측에서 스킵.
        """
        m = off.market
        if m == MarketType.MONEYLINE:
            return fair.fair_probs.get(off.outcome, 0.0), False
        if m == MarketType.MATCH_1X2:
            if sport.has_draw:
                # 축구·하키: Pinnacle 1X2 직접
                return fair.fair_probs.get(off.outcome, 0.0), False
            # 야구 승1패: 포아송 모델로 정시 무/승/패 추정
            if goal_model is None:
                return 0.0, False
            probs = match_1x2_probs(goal_model)
            return probs.get(off.outcome, 0.0), True
        if goal_model is None:
            return 0.0, False  # 파생마켓인데 모델 없음 → 평가 불가
        if m == MarketType.HANDICAP and off.line is not None:
            probs = handicap_probs(goal_model, off.line)
        elif m == MarketType.TOTALS and off.line is not None:
            probs = totals_probs(goal_model, off.line)
        elif m == MarketType.SUM:
            probs = sum_oddeven_probs(goal_model)
        else:
            return 0.0, False
        return probs.get(off.outcome, 0.0), True

    def analyze(self, bundle: NormalizedMatchBundle) -> list[PickAnalysis]:
        offerings = [o for o in bundle.betman_offerings if o.sales_open]
        if not offerings:
            return []

        sport = bundle.match.sport
        calib = calibration_for(sport)

        # 1) Pinnacle 샤프 기준선 de-vig
        fair = compute_fair_line(bundle.overseas_odds, self._devig)
        if not fair.fair_probs:
            return []

        # 파생 마켓(핸디캡/언오버/SUM)용 포아송 득점 모델 역산.
        #  - 3갈래(축구·하키): 1X2 공정확률로 λ 직접 역산
        #  - 야구: 머니라인(2갈래) + 리그 평균 총득점 힌트로 λ 역산
        #  - 농구: 점수 스케일이 커 포아송 부적합 → 미지원(None)
        goal_model = None
        if sport.has_draw:
            goal_model = infer_goal_model(
                fair.fair_probs.get(Outcome.HOME, 0.0),
                fair.fair_probs.get(Outcome.DRAW, 0.0),
                fair.fair_probs.get(Outcome.AWAY, 0.0),
            )
        elif sport == Sport.BASEBALL:
            hint = LEAGUE_TOTAL_HINT.get("baseball", 9.0)
            goal_model = infer_goal_model_2way(
                fair.fair_probs.get(Outcome.HOME, 0.0),
                fair.fair_probs.get(Outcome.AWAY, 0.0),
                hint,
            )

        # 3) Elo 확률 (블렌딩용)
        elo_probs = win_draw_loss_probs(
            self._elo.get(bundle.match.home.id),
            self._elo.get(bundle.match.away.id),
            sport,
        )

        # 5) 비정형 플래그
        flags = self._classifier.classify(bundle)

        # 데이터 신뢰도 (feature 충실도 + 북메이커 수)
        feat_conf = completeness(bundle.features) if bundle.features else 0.0
        book_conf = min(1.0, fair.bookmaker_count / 4.0)
        data_conf = 0.5 * feat_conf + 0.5 * book_conf

        # 라인 무브먼트 (있으면 notes에 반영)
        movement_by_oc = {}
        if bundle.features and bundle.features.common_match.line_movement.present:
            for s in summarize_movements(
                list(bundle.features.common_match.line_movement.value)
            ):
                movement_by_oc[s.outcome] = s

        picks: list[PickAnalysis] = []
        for off in offerings:
            oc = off.outcome

            # 마켓별 공정확률 결정:
            #  - 1X2/머니라인: Pinnacle de-vig 직접 사용 (가장 신뢰도 높음)
            #  - 핸디캡/언오버/SUM: 포아송 모델 추정 (model_based=True)
            fair_p, model_based = self._fair_for(off, fair, goal_model, sport)
            if fair_p <= 0:
                continue
            consensus_p = fair.consensus_probs.get(oc, fair_p)

            # 공정확률 ↔ Elo 블렌딩 (1X2 선택지에만; 파생마켓은 모델값 그대로)
            if model_based:
                blended_p = fair_p
            else:
                elo_p = elo_probs.get(oc, fair_p)
                blended_p = (1 - calib.elo_blend) * fair_p + calib.elo_blend * elo_p

            betman_odds = off.fixed_odds
            betman_implied = 1.0 / betman_odds if betman_odds > 0 else 0.0

            # 2) edge(%) & EV
            #   edge = 공정확률 대비 배당이 주는 초과가치
            edge_pct = (blended_p * betman_odds - 1.0) * 100.0
            #   EV(1원당): 베트맨 환급률 구조에서 fair_p로 평가한 순기대값
            #   = fair_p × (odds−1) − (1−fair_p)
            expected_value = blended_p * (betman_odds - 1.0) - (1.0 - blended_p)

            # 5) 비정형 보조 조정
            sig_adj, used = _signal_adjustment(oc, flags, calib.signal_weight)

            # 4) 평균회귀
            side = "home" if oc == Outcome.HOME else (
                "away" if oc == Outcome.AWAY else "home"
            )
            mr = _mean_reversion_flag(bundle.features, side, sport)
            mr_adj = 0.5 if mr else 0.0

            # 파생마켓은 모델 추정이라 신뢰도를 낮춘다(value 점수에 패널티 계수)
            model_conf = 0.6 if model_based else 1.0

            # 6) value 점수 = edge × 종목가중 × 데이터신뢰 × 모델신뢰 + 보조 + 평균회귀
            value_score = (
                edge_pct * calib.edge_weight * (0.5 + 0.5 * data_conf) * model_conf
                + sig_adj
                + mr_adj
            )

            notes: list[str] = []
            notes.append(f"기준선={fair.source}")
            if model_based:
                lbl = off.market.value
                if off.line is not None:
                    lbl += f" {off.line:+g}" if off.market.value == "handicap" else f" {off.line:g}"
                notes.append(f"모델추정({lbl})")
            if oc in movement_by_oc and not model_based:
                m = movement_by_oc[oc]
                if m.steaming:
                    notes.append(f"라인 쏠림(스팀) {m.drift_pct:+.1f}%")
                elif m.drifting:
                    notes.append(f"라인 이탈 {m.drift_pct:+.1f}%")
            if mr:
                notes.append("평균회귀 후보(기대지표>결과)")
            notes.append(f"데이터신뢰 {data_conf:.0%}")

            picks.append(
                PickAnalysis(
                    match_id=bundle.match.id,
                    market=off.market,
                    outcome=oc,
                    betman_odds=betman_odds,
                    fair_prob=fair_p,
                    consensus_prob=consensus_p,
                    betman_implied_prob=betman_implied,
                    edge_pct=edge_pct,
                    expected_value=expected_value,
                    value_score=value_score,
                    mean_reversion=mr,
                    line=off.line,
                    model_based=model_based,
                    supporting_signals=used,
                    notes=tuple(notes),
                )
            )

        picks.sort(key=lambda p: p.value_score, reverse=True)
        return picks


def analyze_bundles(
    bundles: list[NormalizedMatchBundle],
    analyzer: ValueAnalyzer | None = None,
) -> list[PickAnalysis]:
    analyzer = analyzer or DefaultValueAnalyzer()
    out: list[PickAnalysis] = []
    for b in bundles:
        out.extend(analyzer.analyze(b))
    return out


def payout_note() -> str:
    return (
        f"베트맨 환급률 {BETMAN_PAYOUT_RATE:.0%} → 모든 픽의 장기 EV는 구조적으로 "
        "마이너스입니다. 이 표는 '이기는 픽'이 아니라 '상대적으로 덜 불리한 픽'을 "
        "value 점수로 줄 세운 것입니다."
    )
