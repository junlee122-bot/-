// picks 테이블 행 (대시보드 표시용). Python 분석 레이어가 적재.
export interface Pick {
  pick_id: string;
  match_id: string;
  sport: string;
  league: string | null;
  home_name: string;
  away_name: string;
  start_time: string | null;
  market: string;
  outcome: string; // home | draw | away
  betman_odds: number;
  fair_prob: number; // Pinnacle 기준 공정 확률 (0~1)
  consensus_prob: number;
  betman_implied_prob: number;
  edge_pct: number;
  expected_value: number; // 보통 음수 (환급률 63%)
  value_score: number;
  mean_reversion: boolean;
  line: number | null;
  model_based: boolean;
  is_core: boolean;
  notes: string[] | null;
  signals: { polarity: string; confidence: number; summary: string }[] | null;
  analyzed_at: string;
}

export const OUTCOME_LABEL: Record<string, string> = {
  home: "홈승",
  draw: "무",
  away: "원정승",
};

export const SPORT_LABEL: Record<string, string> = {
  soccer: "축구",
  baseball: "야구",
  basketball: "농구",
  volleyball: "배구",
  hockey: "하키",
  esports: "이스포츠",
};
