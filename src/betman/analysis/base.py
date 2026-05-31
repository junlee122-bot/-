"""분석 레이어 인터페이스 (3단계에서 구현 예정).

파이프라인:
  1) 해외 배당 → 내재확률(1/배당) → de-vig(마진 제거) → 컨센서스 확률
  2) 베트맨 고정배당 + 환급률(63%) → 각 항목 기대값(EV, 마이너스 포함)
  3) 컨센서스 확률 vs 베트맨 배당 갭 → value 점수
  4) 종목 무승부 구조/데이터 신뢰도로 value 점수 보정
  5) LLM 감성 신호(SentimentFlag)를 보조 가중치로 반영
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from ..domain.enums import MarketType, Outcome
from ..domain.models import NewsItem, NormalizedMatchBundle, SentimentFlag


@dataclass(frozen=True)
class PickAnalysis:
    """한 베트맨 선택지에 대한 분석 결과 (출력 레이어가 그대로 표시).

    핵심 전제: 베트맨 환급률(63%) 때문에 expected_value는 대부분 음수다.
    이 시스템은 '이기는 픽'이 아니라 '상대적으로 덜 불리한 픽'을 줄 세운다.
    """

    match_id: str
    market: MarketType
    outcome: Outcome
    betman_odds: float
    # Pinnacle 샤프 기준선 de-vig 공정 확률 = '진짜 확률' 기준
    fair_prob: float
    # 여러 북메이커 컨센서스 de-vig 확률 (라인 쇼핑 평균)
    consensus_prob: float
    betman_implied_prob: float   # 베트맨 배당 내재확률(마진 포함)
    edge_pct: float              # (fair_prob × 배당 − 1) × 100, 보통 음수
    expected_value: float        # 1원당 EV (보통 음수)
    value_score: float           # 클수록 상대적으로 덜 불리 (종목별 캘리브레이션)
    mean_reversion: bool = False  # 기대지표 좋은데 최근 결과 나쁜 팀 신호
    supporting_signals: tuple[SentimentFlag, ...] = ()
    notes: tuple[str, ...] = ()


class DevigStrategy(ABC):
    """해외 배당의 북메이커 마진을 제거하는 전략 (예: 비례/멱승법)."""

    @abstractmethod
    def devig(self, implied_probs: dict[Outcome, float]) -> dict[Outcome, float]:
        ...


class SentimentClassifier(ABC):
    """비정형 원문 → LLM 요약·감성분류 → 신호 플래그."""

    @abstractmethod
    def classify(self, bundle: NormalizedMatchBundle) -> list[SentimentFlag]:
        ...


class ValueAnalyzer(ABC):
    """정규화된 경기 묶음 → 베트맨 선택지별 분석 결과."""

    @abstractmethod
    def analyze(self, bundle: NormalizedMatchBundle) -> list[PickAnalysis]:
        ...
