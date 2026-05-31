"""출력 레이어 인터페이스 (4단계: 웹 대시보드로 구현 예정).

- 축구/야구/농구 기본 섹션, value 점수 순 정렬
- 그 외 종목은 캘리브레이션 기준선 넘는 픽만 '주목 픽' 섹션
- 각 픽: 베트맨 배당 / 내재확률 / EV(−) / value 점수 / 근거 비정형 신호
- 예산 한도 기반 베팅 기록 관리 + 초과 경고
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..analysis.base import PickAnalysis


class BudgetGuard(ABC):
    @abstractmethod
    def remaining(self) -> int | None:
        """남은 예산(KRW). 한도 없으면 None."""

    @abstractmethod
    def check_stake(self, stake_krw: int) -> tuple[bool, str]:
        """베팅 금액이 한도 내인지. (허용여부, 경고메시지)."""


class Presenter(ABC):
    @abstractmethod
    def render(self, picks: list[PickAnalysis]) -> None:
        """분석 결과를 대시보드/화면에 표시."""
