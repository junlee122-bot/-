// 베트맨 발매표 붙여넣기 텍스트 → 발매 항목 파서.
//
// 베트맨이 발매하는 모든 마켓을 인식한다:
//   승무패(1X2) / 핸디캡 / 소수핸디캡 / 언더오버(U/O) / SUM(홀짝)
// 분석 단계에서 Pinnacle 1X2 → 포아송 모델로 파생 마켓 공정확률을 계산해
// 핸디캡·언오버·SUM 도 edge/EV 를 평가한다.

export type Outcome =
  | "home"
  | "draw"
  | "away"
  | "over"
  | "under"
  | "odd"
  | "even";

export type Market = "match_1x2" | "handicap" | "totals" | "sum";

export interface ParsedOffering {
  outcome: Outcome;
  odds: number;
}

export interface ParsedGame {
  gameNo: string;
  home: string;
  away: string;
  market: Market;
  line: number | null; // 핸디캡/언오버 기준점
  marketLabel: string; // 사람이 읽는 마켓명 (미리보기용)
  offerings: ParsedOffering[];
}

const ODDS_RE = /(\d{1,3}\.\d{1,2})/;
const PICK_RE =
  /^(.*?)\s*vs\s*(.+?)(승|무|패|언더|오버|홀|짝)\s*$/i;

interface MarketInfo {
  market: Market;
  line: number | null;
  label: string;
}

// 마켓 헤더 줄 해석. 인식 못 하면 null(그 블록 건너뜀).
function parseMarketHeader(line: string): MarketInfo | null {
  const l = line.trim();
  if (!/^(축구|야구|농구|배구|아이스하키|하키|이스포츠|e스포츠)/.test(l))
    return null;

  // 핸디캡 / 소수핸디캡: "H -1.0", "H +1.0", "H -3.5"
  if (/핸디캡/.test(l)) {
    const m = l.match(/H\s*([+\-]?\d+(?:\.\d+)?)/i);
    const ln = m ? parseFloat(m[1]) : null;
    return { market: "handicap", line: ln, label: l.replace(/^\S+\s*/, "") };
  }
  // 언더오버 U/O 2.5
  if (/언더오버|U\/O/i.test(l)) {
    const m = l.match(/(\d+(?:\.\d+)?)/);
    const ln = m ? parseFloat(m[1]) : null;
    return { market: "totals", line: ln, label: `U/O ${ln ?? ""}` };
  }
  // SUM 홀짝
  if (/SUM/i.test(l)) {
    return { market: "sum", line: null, label: "SUM 홀짝" };
  }
  // 승무패 / 승패
  if (/승무패|승패/.test(l)) {
    return { market: "match_1x2", line: null, label: "승무패" };
  }
  return null;
}

const OUTCOME_MAP: Record<string, Outcome> = {
  승: "home",
  무: "draw",
  패: "away",
  오버: "over",
  언더: "under",
  홀: "odd",
  짝: "even",
};

function normalizeTeam(s: string): string {
  return s
    .replace(/\s+/g, " ")
    .replace(/^[|·\-—\s]+|[|·\-—\s]+$/g, "")
    .trim();
}

export function parseBetmanText(raw: string): ParsedGame[] {
  const lines = raw
    .split("\n")
    .map((l) => l.trim())
    .filter((l) => l.length > 0);

  const games = new Map<string, ParsedGame>();
  let curGameNo = "";
  let curMarket: MarketInfo | null = null;
  let pending: { home: string; away: string; outcome: Outcome } | null = null;

  for (const line of lines) {
    if (/^\d{4,5}$/.test(line)) {
      curGameNo = line;
      curMarket = null;
      pending = null;
      continue;
    }
    if (/^조합|한경기/.test(line)) continue;

    const mh = parseMarketHeader(line);
    if (mh) {
      curMarket = mh;
      pending = null;
      continue;
    }
    if (!curMarket) continue;

    const pick = line.match(PICK_RE);
    const oddsInLine = line.match(ODDS_RE);

    if (pick) {
      const home = normalizeTeam(pick[1]);
      const away = normalizeTeam(pick[2]);
      const outcome = OUTCOME_MAP[pick[3]];
      // 같은 줄에 배당이 붙는 경우: "...승1.14"
      const sameLine = line.match(
        /(승|무|패|언더|오버|홀|짝)\s*(\d{1,3}\.\d{1,2})/
      );
      if (sameLine) {
        addOffering(games, curGameNo, home, away, curMarket, outcome, parseFloat(sameLine[2]));
        pending = null;
      } else {
        pending = { home, away, outcome };
      }
      continue;
    }

    if (oddsInLine && pending) {
      addOffering(
        games,
        curGameNo,
        pending.home,
        pending.away,
        curMarket,
        pending.outcome,
        parseFloat(oddsInLine[1])
      );
      pending = null;
    }
  }

  return Array.from(games.values());
}

function addOffering(
  games: Map<string, ParsedGame>,
  gameNo: string,
  home: string,
  away: string,
  mkt: MarketInfo,
  outcome: Outcome,
  odds: number
) {
  // 게임번호별로 마켓이 다르므로 gameNo 단위로 묶는다
  const key = gameNo || `${home}:${away}:${mkt.label}`;
  let g = games.get(key);
  if (!g) {
    g = {
      gameNo,
      home,
      away,
      market: mkt.market,
      line: mkt.line,
      marketLabel: mkt.label,
      offerings: [],
    };
    games.set(key, g);
  }
  if (g.offerings.some((o) => o.outcome === outcome)) return;
  g.offerings.push({ outcome, odds });
}
