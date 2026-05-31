# Betman Value Analyzer

한국 **베트맨(프로토 승부식) 전용** 스포츠 베팅 가치 분석 시스템.

실제 베팅은 **베트맨에만** 한다는 전제로 설계되었습니다. 해외 사이트 배당은
**참고용(컨센서스/샤프 기준선 확률 추정)** 으로만 사용하며, 해외 베팅을 실행하는
기능은 넣지 않습니다.

> ⚠️ **시스템에 명시된 전제**: 베트맨 환급률은 약 **63%** 입니다.
> 발매되는 모든 항목의 장기 기대값은 **구조적으로 마이너스**이며, 아무리 정보량이
> 많아도 이 환급률의 벽을 넘어 "장기적으로 이익이 나는 베팅"을 만들 수는 없습니다.
> 이 시스템의 목적은 "이기는 베팅"을 찾는 것이 아니라, **여러 마이너스 항목 중
> 상대적으로 덜 불리한(해외 컨센서스 대비 가치 있는) 항목을 골라내고, 각 항목이
> 정확히 얼마나 마이너스인지 투명하게 보여주는 것**입니다.

---

## 4-레이어 아키텍처

각 데이터 소스는 인터페이스로 분리되어 있어 **mock → 유료 API 교체**가 가능합니다.

1. **수집(collection)** — 정형(경기/통계/라인업/부상, 해외 배당, 베트맨 발매·고정배당)
   + 비정형(뉴스/분석글, 정식 API·피드만). 종목 공통 포맷으로 정규화.
2. **저장(storage)** — 과거 회차·경기 통계 누적, 팀별 홈/원정 분리 전적 축적.
   Supabase(Postgres).
3. **분석(analysis)** — Pinnacle 샤프 기준선 de-vig → 공정 확률 → edge%/EV(63% 반영)
   → 종목별 value 점수 → Elo·평균회귀·라인무브먼트·CLV → LLM 비정형 신호(보조).
4. **출력(output)** — 웹 대시보드(예정) + 예산 관리.

---

## 현재 구현 상태 (단계적 진행)

- [x] **0단계** — 폴더 구조 + 4개 레이어 모듈 인터페이스 설계
- [x] **1단계** — 데이터 수집 레이어 (인터페이스 + mock 구현 + 정규화 파이프라인)
- [x] **1.5단계** — 종목별 예측 변수 수집·정규화 (Feature 스키마 + 종목별 가중치
  레지스트리 + 픽별 입력/결과 로깅)
- [x] **2단계** — 저장 레이어 (Supabase/Postgres, 경기·배당·전적·픽로그 누적)
- [x] **3단계** — 분석 레이어 (Pinnacle de-vig / edge% / EV / 종목별 value /
  Elo / 평균회귀 / 라인무브먼트·CLV / LLM 신호)
- [ ] **4단계** — 출력 레이어 (웹 대시보드 + 예산 관리)

---

## 폴더 구조

```
src/betman/
├── config.py                 # 환급률·발매종목·예산·Supabase 설정
├── env.py                    # 의존성 없는 .env 로더
├── domain/
│   ├── enums.py              # Sport, MarketType, Outcome, SignalPolarity ...
│   ├── models.py             # 종목 공통 정규화 모델(Match/Odds/Offering/News ...)
│   └── features.py           # 종목별 예측 변수 스키마(Feature 래퍼, 결측 명시)
├── collection/
│   ├── base.py               # 5개 수집기 인터페이스(ABC)
│   ├── pipeline.py           # 수집기 → NormalizedMatchBundle
│   └── mock/                 # 무료 프로토타입용 mock 구현(match/odds/betman/news/features)
├── storage/
│   ├── base.py               # MatchRepository / PickLogRepository
│   └── supabase_repo.py      # PostgREST(httpx) 기반 구현
├── analysis/
│   ├── base.py               # PickAnalysis + 분석 인터페이스
│   ├── devig.py              # Pinnacle 샤프 기준선 de-vig(비례/멱승법)
│   ├── ratings.py            # 종목별 Elo 레이팅
│   ├── market.py             # 라인 무브먼트 + CLV
│   ├── sentiment.py          # 비정형 → 신호 플래그(LLM/규칙 기반)
│   ├── value.py              # 종목별 value 점수 분석기(전체 결합)
│   ├── weights.py            # 종목별 feature 가중치 레지스트리
│   └── provenance.py         # 픽별 입력/분석/결과/CLV 로깅(JSONL)
└── output/
    └── base.py               # 출력/대시보드 인터페이스(예정)
scripts/
├── run_collection.py         # 1단계 수집 데모
├── run_analysis.py           # 3단계 분석 데모
└── init_supabase.py          # 저장 레이어 점검/스모크 테스트
schema.sql                    # Supabase 테이블 DDL
```

---

## 예측 변수(feature) 스키마

세 종목(축구/야구/농구, 해외 포함)의 예측 변수는 `domain/features.py` 에서
`Feature[T]` 래퍼로 정규화합니다.

- **결측 명시**: 모르면 0이 아니라 `Feature.missing`(`present=False`).
- **항목별 가중치 분리**: feature마다 이름을 가져 `analysis/weights.py` 에서 가중치
  부여 → value 모델을 **종목별로 분리·캘리브레이션**.
- **종목별 핵심 변수에 최고 가중치**: 축구=xG·확정라인업, 야구=선발투수,
  농구=휴식(백투백)·스타결장.
- **비정형은 보조 가중치로만**: 뉴스/분석글을 LLM이 플래그로 환산해 보조 반영.
- **사후 검증 로깅**: 픽별 입력값·가중치·공정확률·edge·EV·결과·CLV를 JSONL로 기록.

| 구분 | 공통(3종목) | 축구 | 야구 | 농구 |
|------|------------|------|------|------|
| 핵심 | 최근폼/H2H/일정/라인무브먼트/부상 | **xG·xGA, 확정라인업** | **선발투수(ERA/FIP/WHIP)** | **휴식·백투백, 스타결장** |
| 보조 | 동기(순위·잔여일정)·더비 | 세트피스·슈팅·심판·날씨·무승부경향·리그정규화 | 불펜피로·좌우스플릿·파크팩터·바람 | 페이스·공수효율·매치업·홈코트 |

신뢰 소스(유료 교체 시): 축구 FBref/Opta·공식 라인업, 야구 Baseball Savant/FanGraphs,
농구 Basketball-Reference/RotoWire, 정형 일원화 Sportradar/Genius Sports.

---

## 분석 레이어 (3단계)

핵심은 **Pinnacle을 샤프 기준선으로** 삼는 것입니다.

1. **de-vig** (`devig.py`): Pinnacle 배당의 마진을 제거한 공정 확률을 '진짜 확률'의
   기준으로 사용(없으면 여러 북메이커 컨센서스로 폴백). 비례/멱승법 지원.
2. **edge% / EV**: 베트맨 고정배당을 공정 확률과 비교해 edge(%)·EV 산출.
   환급률 63% 때문에 **대부분 −EV로 나오는 게 정상**.
3. **Elo** (`ratings.py`): 종목별 파라미터(K·홈어드밴티지·무승부)로 팀 강도 추정,
   공정 확률과 블렌딩.
4. **평균회귀**: 기대 지표(xG/득실)는 좋은데 최근 결과가 나쁜 팀을 신호로 표시.
5. **라인 무브먼트 / CLV** (`market.py`): 개장→종료 라인 이동 추적, 베팅 시점 배당
   vs Pinnacle 종료 공정확률로 CLV(클로징 라인 밸류) 사후 기록.
6. **비정형 신호** (`sentiment.py`): 뉴스를 플래그로 환산해 **보조 가중치로만** 반영
   (`ANTHROPIC_API_KEY` 있으면 LLM, 없으면 규칙 기반 폴백).
7. **종목별 value 점수** (`value.py`): 위를 결합해 종목별로 분리 계산·줄세우기.

> 이 도구는 베팅을 권유하지 않으며, '이기는 픽'이 아니라 '상대적으로 덜 불리한
> 픽'을 value 점수로 줄 세우는 분석 보조입니다.

---

## 실행

```bash
pip install -r requirements.txt        # 수집/분석 데모는 표준 라이브러리만으로도 동작
python -m scripts.run_collection       # 1단계: 수집·정규화 데모
python -m scripts.run_analysis         # 3단계: de-vig/edge/EV/value/CLV 데모
```

mock 수집기가 축구·야구·농구 등 경기를 생성하고, 분석 레이어가 Pinnacle 기준
공정확률·edge·EV·value 점수를 계산해 종목별로 줄 세웁니다. 결과는
`data/analysis_log.jsonl` 에 픽별 입력/분석/CLV 로그로 누적됩니다.

---

## 저장 레이어 (Supabase)

과거 회차·경기 통계, 팀별 홈/원정 전적, 픽 입력/결과 로그를 Supabase(Postgres)에
누적합니다. PostgREST REST API + service_role 키를 사용합니다.

**1) 스키마 생성 (최초 1회)**: Supabase 대시보드 → SQL Editor 에서 `schema.sql`
전체를 실행합니다. (REST API로는 DDL(CREATE TABLE)이 불가하여 1회 수동 실행 필요.)

**2) 키 설정**: `.env.example` 을 `.env` 로 복사해 채웁니다. `.env` 는 `.gitignore`
되므로 커밋되지 않습니다.

```bash
cp .env.example .env
# .env 편집:
#   SUPABASE_URL=https://<ref>.supabase.co
#   SUPABASE_SERVICE_ROLE_KEY=<service_role_jwt>   # 서버 사이드 전용, 노출 금지
```

**3) 점검/스모크 테스트** (네트워크가 열린 환경에서):

```bash
pip install -r requirements.txt        # httpx
python -m scripts.init_supabase
```

> ⚠️ 보안: `service_role` 키는 RLS를 우회하므로 **서버 사이드에서만** 사용하고,
> 코드·커밋·클라이언트에 절대 포함하지 않습니다. 비밀키는 `.env`(환경변수)로만
> 주입합니다. 테이블: teams / matches / betman_offerings / overseas_odds /
> team_records / pick_logs.

---

## 예산 구성안 (참고)

현재는 **무료 / mock 데이터**로 전체 구조를 검증합니다. 유료 API 교체 시:

| 월 예산 | 해외 배당 | 정형 통계 | 비정형(뉴스) |
|--------|-----------|-----------|--------------|
| ~$0 (현재) | mock | mock | mock |
| ~$50 | The Odds API 저가 | 무료/저가 스탯 | 무료 RSS/피드 |
| ~$200 | The Odds API 유료 | 통계 API 기본 | 뉴스 API |
| ~$500 | OddsJam급 | Sportradar/Opta | 뉴스 API 풀 |

모든 외부 수집은 **정식 API/허용된 피드만** 사용합니다. 무단 스크래핑은 쓰지 않습니다.
