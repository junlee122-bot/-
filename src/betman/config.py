"""시스템 전역 설정.

핵심 전제(환급률 63%)와 발매 종목, 예산을 한곳에서 관리한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import env
from .domain.enums import Sport


# 베트맨 프로토 승부식 환급률. 모든 EV 계산의 기준이 되는 '넘을 수 없는 벽'.
BETMAN_PAYOUT_RATE: float = 0.63


@dataclass
class AppConfig:
    # 분석 대상: 베트맨에 발매되는 전 종목
    sports: list[Sport] = field(
        default_factory=lambda: [
            Sport.SOCCER,
            Sport.BASEBALL,
            Sport.BASKETBALL,
            Sport.VOLLEYBALL,
            Sport.HOCKEY,
            Sport.ESPORTS,
        ]
    )

    # 환급률 (장기 기대값의 구조적 상한)
    payout_rate: float = BETMAN_PAYOUT_RATE

    # 출력 시 기본 섹션으로 항상 보여줄 핵심 종목
    core_sports: list[Sport] = field(
        default_factory=lambda: [Sport.SOCCER, Sport.BASEBALL, Sport.BASKETBALL]
    )

    # 예산 관리 (4단계에서 사용). 단위: KRW. None이면 한도 없음.
    monthly_budget_krw: int | None = None

    # 데이터 소스 모드: "mock" | "live"
    # live로 바꾸면 collection 레이어가 유료 API 구현으로 교체된다.
    data_source_mode: str = "mock"


DEFAULT_CONFIG = AppConfig()


@dataclass
class SupabaseSettings:
    """Supabase 접속 설정. 값은 환경변수/.env 에서만 읽는다 (코드에 비밀키 금지)."""

    url: str | None = None
    service_role_key: str | None = None
    anon_key: str | None = None

    @property
    def configured(self) -> bool:
        return bool(self.url and (self.service_role_key or self.anon_key))

    @property
    def write_key(self) -> str | None:
        """쓰기/적재용 키 (service_role 우선, 없으면 anon)."""
        return self.service_role_key or self.anon_key


def load_supabase_settings() -> SupabaseSettings:
    """.env 를 로드한 뒤 환경변수에서 Supabase 설정을 읽어온다."""
    env.load_dotenv()
    return SupabaseSettings(
        url=env.get("SUPABASE_URL"),
        service_role_key=env.get("SUPABASE_SERVICE_ROLE_KEY"),
        anon_key=env.get("SUPABASE_ANON_KEY"),
    )
