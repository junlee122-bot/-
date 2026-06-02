"""베팅액 추천(켈리) + 사람이 읽는 설명 생성.

두 가지 켈리 비율을 계산한다:

1) kelly_aggressive (환급률 무시):
   해외 공정확률 p(샤프 기준)와 베트맨 배당 b 로 표준 켈리.
     f = (b·p − 1) / (b − 1)          (b = 십진배당, net = b−1)
   p·b > 1 (해외 기준 우위)일 때만 양수. "이론상 우위가 있다면 이만큼" 의 의미.
   변동성을 줄이려고 1/4 켈리(fractional)를 적용한다.

2) kelly_realistic (환급률 63% 반영):
   베트맨은 장기적으로 받는 배당이 공정가의 환급률 수준이라, 실효 배당을
   b_eff = 1 + (b−1)·payout 로 보수적으로 본다. 이 b_eff 로 켈리를 계산하면
   거의 항상 0 이하(=베팅 비권장)가 된다. 음수면 0 으로 자른다.

둘 다 자금 대비 '비율'을 돌려준다. 화면에서 자금×비율 로 금액을 만든다.
과도 베팅 방지를 위해 상한(cap)을 둔다.
"""

from __future__ import annotations

from ..config import BETMAN_PAYOUT_RATE
from ..domain.enums import MarketType, Outcome

# 변동성 완화용 분수 켈리 (1/4 켈리)
_KELLY_FRACTION = 0.25
# 한 픽 최대 베팅 비율 상한 (자금의 5%)
_KELLY_CAP = 0.05


def _kelly_fraction(prob: float, decimal_odds: float) -> float:
    """표준 켈리 비율 (양수만, 분수·상한 적용)."""
    net = decimal_odds - 1.0
    if net <= 0 or prob <= 0:
        return 0.0
    f = (decimal_odds * prob - 1.0) / net
    if f <= 0:
        return 0.0
    return min(f * _KELLY_FRACTION, _KELLY_CAP)


def kelly_pair(fair_prob: float, betman_odds: float) -> tuple[float, float]:
    """(공격적[환급률 무시], 현실[환급률 반영]) 켈리 비율."""
    aggressive = _kelly_fraction(fair_prob, betman_odds)
    # 환급률 반영 실효 배당
    eff_odds = 1.0 + (betman_odds - 1.0) * BETMAN_PAYOUT_RATE
    realistic = _kelly_fraction(fair_prob, eff_odds)
    return aggressive, realistic


# --------------------------------------------------------------------------- #
# 사람이 읽는 설명
# --------------------------------------------------------------------------- #
_OUTCOME_KO = {
    Outcome.HOME: "홈 승",
    Outcome.DRAW: "무승부",
    Outcome.AWAY: "원정 승",
    Outcome.OVER: "오버",
    Outcome.UNDER: "언더",
    Outcome.ODD: "홀",
    Outcome.EVEN: "짝",
}
_MARKET_KO = {
    MarketType.MATCH_1X2: "승무패",
    MarketType.MONEYLINE: "승패",
    MarketType.HANDICAP: "핸디캡",
    MarketType.TOTALS: "언더오버",
    MarketType.SUM: "홀짝",
}


def build_explanation(
    *,
    home: str,
    away: str,
    market: MarketType,
    outcome: Outcome,
    line: float | None,
    betman_odds: float,
    fair_prob: float,
    edge_pct: float,
    expected_value: float,
    model_based: bool,
) -> str:
    """한 픽을 일상어로 설명하는 한 문단."""
    oc_ko = _OUTCOME_KO.get(outcome, outcome.value)
    mk_ko = _MARKET_KO.get(market, market.value)
    line_txt = ""
    if line is not None:
        line_txt = f" {line:+g}" if market == MarketType.HANDICAP else f" {line:g}"

    fair_pct = fair_prob * 100
    implied = (1.0 / betman_odds) * 100 if betman_odds > 0 else 0
    # 베트맨 배당이 암시하는 확률 vs 해외(샤프) 공정확률 비교
    parts: list[str] = []
    parts.append(
        f"{home} vs {away} — '{mk_ko}{line_txt} {oc_ko}' 에 베트맨 배당 "
        f"{betman_odds:.2f}배."
    )
    parts.append(
        f"이 배당은 '{implied:.0f}% 확률'을 의미하는데, 해외 샤프 시장 기준 실제 "
        f"확률은 약 {fair_pct:.0f}% 로 추정됩니다."
    )
    if edge_pct >= 0:
        parts.append(
            f"즉 해외 기준으로는 배당이 {edge_pct:+.0f}% 만큼 후하게 매겨져 "
            f"'상대적으로 가치 있는' 쪽입니다."
        )
    else:
        parts.append(
            f"해외 기준으로도 배당이 {edge_pct:.0f}% 불리해 가치가 낮습니다."
        )
    # EV 는 환급률 반영 — 거의 항상 마이너스
    parts.append(
        f"단, 베트맨 환급률(63%)을 반영한 실제 기대값은 1만원당 "
        f"{expected_value*10000:,.0f}원으로, 장기적으로는 {'손실' if expected_value < 0 else '이익'}입니다."
    )
    if model_based:
        parts.append("(이 마켓은 포아송 모델 추정값이라 신뢰도가 낮습니다.)")
    return " ".join(parts)
