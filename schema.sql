-- Betman Value Analyzer — Supabase(Postgres) 스키마
--
-- 적용 방법(한 번만):
--   Supabase 대시보드 → SQL Editor 에 이 파일 전체를 붙여넣고 Run.
--   (PostgREST REST API로는 DDL(CREATE TABLE)을 실행할 수 없어, 스키마 생성은
--    SQL Editor 또는 psql로 1회 수행해야 한다. 이후 데이터 입출력은 service_role
--    키로 REST를 통해 코드가 수행한다.)
--
-- 설계: 과거 회차·경기 통계를 누적하고, 팀별 홈/원정 분리 전적을 축적한다.

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

-- 픽 입력/결과 로그 (사후 검증·백테스트) --------------------------------
create table if not exists pick_logs (
    pick_id        text primary key,
    match_id       text,
    sport          text,
    market         text,
    outcome        text,
    betman_odds    numeric,
    features       jsonb,                -- 사용한 feature 값 + 가중치 + 결측 여부
    result_outcome text,                 -- 경기 후 채움
    hit            boolean,              -- 경기 후 채움
    captured_at    timestamptz,
    recorded_at    timestamptz not null default now()
);
create index if not exists idx_picklogs_match on pick_logs (match_id);

-- 비고: service_role 키는 RLS를 우회한다. anon 키로도 접근하게 하려면 아래처럼
-- RLS와 정책을 명시적으로 추가할 것(기본은 service_role 전용으로 두는 게 안전).
-- alter table matches enable row level security;
