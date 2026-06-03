// 베트맨 발매표 붙여넣기 텍스트 → 발매 항목 파서.
//
// 베트맨의 두 가지 화면 포맷을 모두 인식한다:
//   (A) 옛 상세형: "팀A vs 팀B승  1.14"  (팀명+선택지 한 줄, 배당 근처)
//   (B) 새 목록형: "두산 vs 한화 야구 승패 메뉴 열기" 줄로 팀/종목/마켓을 잡고,
//                  그 뒤에 "승\n2.43\n패\n1.38" 처럼 선택지·배당이 별도 줄.
// 종목·마켓(승패/승무패/핸디캡/언더오버/SUM)을 자동 인식한다.

export type Outcome =
  | "home"
  | "draw"
  | "away"
  | "over"
  | "under"
  | "odd"
  | "even";

export type Market = "match_1x2" | "moneyline" | "handicap" | "totals" | "sum";
export type Sport =
  | "soccer"
  | "baseball"
  | "basketball"
  | "volleyball"
  | "hockey"
  | "esports";

export interface ParsedOffering {
  outcome: Outcome;
  odds: number;
}

export interface ParsedGame {
  gameNo: string;
  sport: Sport;
  home: string;
  away: string;
  market: Market;
  line: number | null;
  marketLabel: string;
  offerings: ParsedOffering[];
}

const ODDS_RE = /^(\d{1,3}\.\d{1,2})$/; // 한 줄이 통째로 배당
const ODDS_ANY = /(\d{1,3}\.\d{1,2})/;
// 옛 포맷: "팀 vs 팀<선택지>" (선택지가 팀명 뒤에 붙음)
const OLD_PICK_RE = /^(.*?)\s*vs\s*(.+?)(승|무|패|언더|오버|홀|짝|1)\s*$/i;
// 새 포맷 앵커: "팀A vs 팀B  <종목> <마켓...> 메뉴 열기"
const MENU_RE =
  /^(.+?)\s+vs\s+(.+?)\s+(축구|야구|농구|배구|아이스하키|하키|이스포츠)\s+(.+?)\s*메뉴\s*열기\s*$/;

const SPORT_KO: Record<string, Sport> = {
  축구: "soccer",
  야구: "baseball",
  농구: "basketball",
  배구: "volleyball",
  아이스하키: "hockey",
  하키: "hockey",
  이스포츠: "esports",
  e스포츠: "esports",
};

const OUTCOME_MAP: Record<string, Outcome> = {
  승: "home",
  무: "draw",
  "1": "draw",
  패: "away",
  오버: "over",
  언더: "under",
  홀: "odd",
  짝: "even",
};

interface MarketInfo {
  market: Market;
  line: number | null;
  label: string;
}

// 마켓 설명 문자열("승패","승무패","세트핸디캡","언더오버U/O 2.5","SUM"...) 해석.
function parseMarketDesc(desc: string, handicapLine: number | null): MarketInfo | null {
  const d = desc.trim();
  // 전반/후반/이닝/쿼터/세트수 등 부분경기는 제외 (단 '세트핸디캡'은 허용)
  if (/전반|후반|이닝|쿼터/.test(d)) return null;
  if (/핸디캡/.test(d)) {
    // desc 안에 H 값이 있으면 우선, 없으면 직전에 본 H 줄 사용
    const m = d.match(/H\s*([+\-]?\d+(?:\.\d+)?)/i);
    const ln = m ? parseFloat(m[1]) : handicapLine;
    return { market: "handicap", line: ln, label: `핸디캡 ${ln ?? ""}` };
  }
  if (/언더오버|U\/O/i.test(d)) {
    const m = d.match(/(\d+(?:\.\d+)?)/);
    const ln = m ? parseFloat(m[1]) : null;
    return { market: "totals", line: ln, label: `U/O ${ln ?? ""}` };
  }
  if (/SUM/i.test(d)) return { market: "sum", line: null, label: "SUM 홀짝" };
  if (/승무패/.test(d)) return { market: "match_1x2", line: null, label: "승무패" };
  if (/승1패/.test(d)) return { market: "match_1x2", line: null, label: "승무패" };
  if (/승패/.test(d)) return { market: "moneyline", line: null, label: "승패" };
  return null;
}

function normTeam(s: string): string {
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

  let gameNo = "";
  let cur: ParsedGame | null = null; // 현재 채우는 중인 게임
  let pendingOutcome: Outcome | null = null;
  let pendingHandicapLine: number | null = null;
  let curKeySport: Sport | null = null; // 직전 종목 단어(헤더용)

  const keyOf = (
    g: { gameNo: string; sport: Sport; home: string; away: string; market: Market; line: number | null }
  ) =>
    g.gameNo
      ? g.gameNo
      : `${g.sport}:${g.home}:${g.away}:${g.market}:${g.line ?? ""}`;

  for (const line of lines) {
    // 잡음 스킵
    if (/^조합|메뉴 열기$|상세보기|팝업 열기|배당률 변동|긴급 공지|주의사항|상세내용 열기|더보기$/.test(line)) {
      // '메뉴 열기' 단독, '...더보기' 등
      if (line.endsWith("더보기")) {
        // 게임 블록 종료
        cur = null;
        pendingOutcome = null;
      }
      continue;
    }
    if (line.endsWith("더보기")) {
      cur = null;
      pendingOutcome = null;
      continue;
    }
    if (/^배당률\s*(하락|상승)/.test(line)) continue;

    // 종목 단독 줄
    if (SPORT_KO[line]) {
      curKeySport = SPORT_KO[line];
      continue;
    }
    // 게임번호 단독
    if (/^\d{4,5}$/.test(line)) {
      gameNo = line;
      continue;
    }
    // 핸디캡 H 값 단독 줄
    const hm = line.match(/^H\s*([+\-]?\d+(?:\.\d+)?)$/i);
    if (hm) {
      pendingHandicapLine = parseFloat(hm[1]);
      continue;
    }

    // (B) 새 목록형 앵커: "팀 vs 팀 종목 마켓 메뉴 열기"
    const menu = line.match(MENU_RE);
    if (menu) {
      const home = normTeam(menu[1]);
      const away = normTeam(menu[2]);
      const sport = SPORT_KO[menu[3]] ?? curKeySport ?? "baseball";
      const mi = parseMarketDesc(menu[4], pendingHandicapLine);
      pendingHandicapLine = null;
      pendingOutcome = null;
      if (!mi) {
        cur = null;
        continue;
      }
      cur = {
        gameNo,
        sport,
        home,
        away,
        market: mi.market,
        line: mi.line,
        marketLabel: mi.label,
        offerings: [],
      };
      games.set(keyOf(cur), cur);
      continue;
    }

    // (A) 옛 상세형: "팀 vs 팀<선택지>" + (같은 줄/다음 줄 배당)
    const old = line.match(OLD_PICK_RE);
    if (old && !/메뉴|더보기/.test(line)) {
      const home = normTeam(old[1]);
      const away = normTeam(old[2]);
      const oc = OUTCOME_MAP[old[3]];
      const sport = curKeySport ?? "baseball";
      // 마켓 추정: 선택지가 무/승/패면 1x2 또는 moneyline (무 있으면 1x2)
      const market: Market =
        old[3] === "무" || old[3] === "1" ? "match_1x2" : "moneyline";
      if (!cur || cur.home !== home || cur.away !== away) {
        cur = {
          gameNo,
          sport,
          home,
          away,
          market,
          line: null,
          marketLabel: market === "match_1x2" ? "승무패" : "승패",
          offerings: [],
        };
        games.set(keyOf(cur), cur);
      }
      const sl = line.match(/(승|무|패|언더|오버|홀|짝|1)\s*(\d{1,3}\.\d{1,2})/);
      if (sl) {
        addOffering(cur, oc, parseFloat(sl[2]));
        pendingOutcome = null;
      } else {
        pendingOutcome = oc;
      }
      continue;
    }

    // 선택지 단독 줄 (새 포맷)
    if (OUTCOME_MAP[line] !== undefined && cur) {
      pendingOutcome = OUTCOME_MAP[line];
      continue;
    }

    // 배당 단독 줄 → 직전 선택지에 연결
    if (ODDS_RE.test(line) && cur && pendingOutcome) {
      addOffering(cur, pendingOutcome, parseFloat(line));
      pendingOutcome = null;
      continue;
    }
    // 배당이 섞인 줄(드묾)
    const anyOdds = line.match(ODDS_ANY);
    if (anyOdds && cur && pendingOutcome) {
      addOffering(cur, pendingOutcome, parseFloat(anyOdds[1]));
      pendingOutcome = null;
    }
  }

  // 선택지가 하나도 없는 게임 제거
  return Array.from(games.values()).filter((g) => g.offerings.length > 0);
}

function addOffering(g: ParsedGame, outcome: Outcome, odds: number) {
  if (g.offerings.some((o) => o.outcome === outcome)) return;
  g.offerings.push({ outcome, odds });
}
