"""저장 레이어 인터페이스 (2단계에서 SQLite 등으로 구현 예정).

과거 회차·경기 통계를 누적하고, 팀별 홈/원정 분리 전적을 조회한다.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..domain.enums import Sport
from ..domain.models import NormalizedMatchBundle, TeamRecord


class MatchRepository(ABC):
    @abstractmethod
    def save_bundles(self, bundles: list[NormalizedMatchBundle]) -> None:
        """수집된 경기 묶음을 누적 저장."""

    @abstractmethod
    def get_team_record(
        self, team_id: str, sport: Sport, venue: str = "overall"
    ) -> TeamRecord:
        """팀별 전적 조회 (venue: home/away/overall)."""
