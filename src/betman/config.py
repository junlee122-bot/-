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
    # live로 바꾸면 해외 배당=The Odds API, 뉴스=RSS 로 교체된다.
    # (베트맨 발매·정형 통계는 실 API가 없어 mock 유지 — 어댑터 docstring 참고)
    data_source_mode: str = "mock"


DEFAULT_CONFIG = AppConfig()


def load_app_config() -> AppConfig:
    """기본 설정에 .env 의 DATA_SOURCE_MODE 를 반영해 반환."""
    env.load_dotenv()
    cfg = AppConfig()
    mode = env.get("DATA_SOURCE_MODE")
    if mode in ("mock", "live"):
        cfg.data_source_mode = mode
    return cfg


# --------------------------------------------------------------------------- #
# The Odds API (해외 배당, 무료 티어 월 500요청) 설정
# --------------------------------------------------------------------------- #
# 우리 Sport enum → The Odds API sport key 목록 (여러 리그 합산 가능).
# /v4/sports 응답 기준. 시즌/커버리지에 따라 비활성일 수 있음(그 종목은 0건).
ODDS_API_SPORT_KEYS: dict[Sport, list[str]] = {
    Sport.SOCCER: [
        "soccer_japan_j_league",
        "soccer_epl",
        "soccer_spain_la_liga",
        "soccer_italy_serie_a",
    ],
    Sport.BASEBALL: ["baseball_kbo", "baseball_mlb", "baseball_npb"],
    Sport.BASKETBALL: ["basketball_nba"],
    # 아래는 The Odds API 미지원/불안정 → 라이브에서 빈 결과(=mock 폴백 권장)
    Sport.VOLLEYBALL: [],
    Sport.HOCKEY: ["icehockey_nhl"],
    Sport.ESPORTS: [],
}


@dataclass
class OddsApiSettings:
    api_key: str | None = None
    # eu 리전에 Pinnacle이 포함됨 (샤프 기준선). us 추가 시 미국 북 다수.
    regions: str = "eu"
    cache_ttl_sec: int = 600          # 같은 종목 재호출 캐시(쿼터 절약)

    @property
    def configured(self) -> bool:
        return bool(self.api_key)


@dataclass
class RssSettings:
    # 종목별 RSS 피드 URL. 정식/허용된 피드만 사용(무단 스크래핑 금지).
    # 기본은 비워두고 .env 또는 코드에서 주입 (피드 URL은 환경마다 다름).
    feeds: dict[Sport, list[str]] = field(default_factory=dict)
    timeout_sec: int = 10
    max_items_per_feed: int = 50


def load_odds_api_settings() -> OddsApiSettings:
    env.load_dotenv()
    return OddsApiSettings(
        api_key=env.get("ODDS_API_KEY"),
        regions=env.get("ODDS_API_REGIONS", "eu") or "eu",
    )


def load_rss_settings() -> RssSettings:
    """RSS 피드를 .env 의 RSS_FEEDS_<SPORT> (콤마 구분) 에서 읽는다.

    예) RSS_FEEDS_BASEBALL=https://a/rss,https://b/rss
    """
    env.load_dotenv()
    feeds: dict[Sport, list[str]] = {}
    for sport in Sport:
        raw = env.get(f"RSS_FEEDS_{sport.name}")
        if raw:
            feeds[sport] = [u.strip() for u in raw.split(",") if u.strip()]
    return RssSettings(feeds=feeds)


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
