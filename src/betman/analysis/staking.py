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
    """한 픽을 아주 쉬운 말로 설명한다. 용어 대신 비유, 결론 먼저."""
    oc_ko = _OUTCOME_KO.get(outcome, outcome.value)
    mk_ko = _MARKET_KO.get(market, market.value)
    line_txt = ""
    if line is not None:
        line_txt = f" {line:+g}" if market == MarketType.HANDICAP else f" {line:g}"

    fair_pct = round(fair_prob * 100)
    implied = round((1.0 / betman_odds) * 100) if betman_odds > 0 else 0
    loss_per_10k = expected_value * 10000  # 1만원당 평균 손익(원)

    parts: list[str] = []

    # 1) 무엇에 거는 건지
    parts.append(
        f"이건 「{home} vs {away}」 경기에서 ‘{mk_ko}{line_txt} {oc_ko}’ 에 "
        f"거는 겁니다. 맞으면 1만원이 {betman_odds*10000:,.0f}원이 됩니다."
    )

    # 2) 베트맨 배당이 보는 확률 vs 진짜 실력 비교 (쉬운 비유)
    parts.append(
        f"베트맨은 이게 100번 중 약 {implied}번 일어난다고 보고 배당을 매겼는데, "
        f"해외 큰손들의 배당을 보면 실제로는 100번 중 약 {fair_pct}번 일어날 "
        f"일입니다."
    )

    # 3) 그래서 싼가 비싼가 (가격 비유)
    if edge_pct >= 0:
        parts.append(
            f"즉 실제 가치보다 배당을 후하게 쳐줘서, 다른 항목들보다 "
            f"‘그나마 덜 손해 보는’ 쪽입니다."
        )
    else:
        parts.append(
            "즉 실제 가치보다 배당이 박해서, 별로 살 만한 항목이 아닙니다."
        )

    # 4) 그래도 결국 환급률 때문에 장기 손해 (핵심, 솔직하게)
    if loss_per_10k < 0:
        parts.append(
            f"하지만 베트맨은 건 돈의 약 37%를 수수료처럼 떼갑니다(환급률 63%). "
            f"그래서 이 항목도 1만원을 걸면 평균적으로 "
            f"{abs(loss_per_10k):,.0f}원쯤 잃는 게 정상입니다. "
            f"즉 ‘잘 고른 손해’지 ‘버는 픽’이 아닙니다."
        )
    else:
        parts.append(
            f"드물게 환급률을 감안해도 평균 +{loss_per_10k:,.0f}원으로 살짝 유리한 "
            f"항목이지만, 표본·모델 오차를 감안하면 확신은 금물입니다."
        )

    # 5) 모델 추정 경고
    if model_based:
        parts.append(
            "참고로 이 마켓(핸디캡·언더오버·홀짝 등)은 직접 비교할 해외 배당이 "
            "없어 계산으로 추정한 값이라, 숫자를 그대로 믿기 어렵습니다."
        )

    return " ".join(parts)

