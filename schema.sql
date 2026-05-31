-- Betman Value Analyzer — Supabase(Postgres) 스키마
--
-- 적용 방법(한 번만):
--   Supabase 대시보드 → SQL Editor 에 이 파일 전체를 붙여넣고 Run.
--   (PostgREST REST API로는 DDL(CREATE TABLE)을 실행할 수 없어, 스키마 생성은
--    SQL Editor 또는 psql로 1회 수행해야 한다. 이후 데이터 입출력은 service_role
--    키로 REST를 통해 코드가 수행한다.)
--
-- 설계: 과거 회차·경기 통계를 누적하고, 팀별 홈/원정 분리 전적을 축적한다.
--       분석 결과(picks)는 대시보드가 읽어 종목별로 표시한다.

-- 팀 ----------------------------------------------------------------------
create table if not exists teams (
    id    text primary key,
    name  text not null,
    sport text not null
);

-- 경기 --------------------------------------------------------------------
create table if not exists matches (
    id            text primary key,
    sport         text not null,
    league        text,
    home_team_id  text references teams(id),
    away_team_id  text references teams(id),
    start_time    timestamptz,
    status        text,
    inserted_at   timestamptz not null default now()
);
create index if not exists idx_matches_sport_start on matches (sport, start_time);

-- 베트맨 발매·고정배당 (실제 베팅 대상) ----------------------------------
create table if not exists betman_offerings (
    id          bigserial primary key,
    match_id    text references matches(id),
    round_no    text,
    market      text,
    outcome     text,
    fixed_odds  numeric,
    sales_open  boolean,
    captured_at timestamptz not null default now()
);
create index if not exists idx_betman_match on betman_offerings (match_id);

-- 해외 북메이커 배당 (참고용, 라인 무브먼트 시계열) ----------------------
create table if not exists overseas_odds (
    id           bigserial primary key,
    match_id     text references matches(id),
    bookmaker    text,
    market       text,
    outcome      text,
    decimal_odds numeric,
    captured_at  timestamptz not null default now()
);
create index if not exists idx_odds_match on overseas_odds (match_id);

-- 팀별 전적 (홈/원정/전체 분리, 누적) ------------------------------------
create table if not exists team_records (
    team_id    text not null,
    sport      text not null,
    venue      text not null,            -- 'home' | 'away' | 'overall'
    wins       integer not null default 0,
    draws      integer not null default 0,
    losses     integer not null default 0,
    updated_at timestamptz not null default now(),
    primary key (team_id, venue)
);

-- 분석 결과 픽 (대시보드 표시용) -----------------------------------------
-- 분석 레이어가 산출한 PickAnalysis 1건 = 1행. 표시에 필요한 정보를 비정규화해
-- 담아 대시보드가 join 없이 바로 읽을 수 있게 한다.
create table if not exists picks (
    pick_id             text primary key,    -- "<match_id>:<outcome>"
    match_id            text,
    sport               text,
    league              text,
    home_name           text,
    away_name           text,
    start_time          timestamptz,
    market              text,
    outcome             text,
    betman_odds         numeric,
    fair_prob           numeric,             -- Pinnacle 기준 공정 확률
    consensus_prob      numeric,
    betman_implied_prob numeric,
    edge_pct            numeric,
    expected_value      numeric,             -- 보통 음수 (환급률 63%)
    value_score         numeric,
    mean_reversion      boolean default false,
    is_core             boolean default false,
    notes               jsonb,
    signals             jsonb,               -- 근거 비정형 신호
    analyzed_at         timestamptz not null default now()
);
create index if not exists idx_picks_sport_value on picks (sport, value_score desc);

-- 픽 입력/결과 로그 (사후 검증·백테스트) --------------------------------
create table if not exists pick_logs (
    pick_id        text primary key,
    match_id       text,
    sport          text,
    market         text,
    outcome        text,
    betman_odds    numeric,
    features       jsonb,                -- 사용한 feature 값 + 가중치 + 결측 여부
    fair_prob      numeric,
    edge_pct       numeric,
    expected_value numeric,
    value_score    numeric,
    result_outcome text,                 -- 경기 후 채움
    hit            boolean,              -- 경기 후 채움
    clv_pct        numeric,              -- 베팅 후 채움 (Pinnacle 종료 대비)
    beat_closing   boolean,
    captured_at    timestamptz,
    recorded_at    timestamptz not null default now()
);
create index if not exists idx_picklogs_match on pick_logs (match_id);

-- 베팅 기록 (예산 관리) --------------------------------------------------
create table if not exists bets (
    id          bigserial primary key,
    pick_id     text,
    stake_krw   integer not null,
    odds        numeric,
    placed_at   timestamptz not null default now(),
    result      text,                    -- 'win' | 'lose' | 'void' | null
    payout_krw  integer
);

-- 베트맨 수동 입력 발매 배당 (대시보드 붙여넣기 → 파이프라인이 팀명 매칭) ---
-- 웹에서 붙여넣은 시점엔 The Odds API match_id 를 모르므로 FK 없이 팀명으로
-- 저장한다. run_full_pipeline 이 팀명(aliases)으로 실제 경기와 매칭한다.
create table if not exists betman_manual_odds (
    id          bigserial primary key,
    round_no    text,
    sport       text not null,            -- soccer|baseball|basketball|...
    home        text not null,            -- 베트맨 표기(한글 가능)
    away        text not null,
    outcome     text not null,            -- home|draw|away
    odds        numeric not null,
    game_no     text,                     -- 베트맨 게임번호(참고)
    sales_open  boolean default true,
    created_at  timestamptz not null default now(),
    unique (round_no, sport, home, away, outcome)
);
create index if not exists idx_manual_round on betman_manual_odds (round_no);

-- 비고: service_role 키는 RLS를 우회한다. anon 키로도 접근하게 하려면 RLS와
-- 정책을 명시적으로 추가할 것(기본은 service_role 전용으로 두는 게 안전).
-- 대시보드(Next.js)는 서버 컴포넌트에서 service_role 키로 읽으므로 키가
-- 클라이언트에 노출되지 않는다.
