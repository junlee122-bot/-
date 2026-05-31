"""저장 레이어 인터페이스.

과거 회차·경기 통계를 누적하고, 팀별 홈/원정 분리 전적을 조회한다.
구현체: SupabaseMatchRepository (Postgres) / 향후 SQLite 등 교체 가능.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from ..domain.enums import Outcome, Sport
from ..domain.models import NormalizedMatchBundle, TeamRecord


class MatchRepository(ABC):
    @abstractmethod
    def save_bundles(self, bundles: list[NormalizedMatchBundle]) -> None:
        """수집된 경기 묶음을 누적 저장."""

    @abstractmethod
    def get_team_record(
        self, team_id: str, sport: Sport, venue: str = "overall"
    ) -> TeamRecord:
        """팀별 전적 조회 (venue: home/away/overall). 없으면 빈 전적."""

    @abstractmethod
    def upsert_team_record(self, record: TeamRecord) -> None:
        """팀별 전적 갱신(누적)."""


class PickLogRepository(ABC):
    """픽별 입력값/결과 로그 저장 (사후 검증·백테스트)."""

    @abstractmethod
    def save_pick_snapshot(self, snapshot: dict) -> None:
        """픽 입력 스냅샷 1건 저장(upsert)."""

    @abstractmethod
    def record_pick_result(
        self, pick_id: str, result_outcome: Outcome, hit: bool
    ) -> None:
        """경기 후 픽 결과 기록."""

    @abstractmethod
    def get_pick(self, pick_id: str) -> Optional[dict]:
        """픽 로그 조회."""
