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
from dataclasses import dataclass

from ..domain.enums import MarketType, Outcome
from ..domain.models import NewsItem, NormalizedMatchBundle, SentimentFlag


@dataclass(frozen=True)
class PickAnalysis:
    """한 베트맨 선택지에 대한 분석 결과 (출력 레이어가 그대로 표시)."""

    match_id: str
    market: MarketType
    outcome: Outcome
    betman_odds: float
    consensus_prob: float        # de-vig된 해외 컨센서스 확률
    expected_value: float        # EV (환급률 반영, 보통 음수)
    value_score: float           # 클수록 상대적으로 덜 불리
    supporting_signals: tuple[SentimentFlag, ...] = ()


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
