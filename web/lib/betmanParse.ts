// 베트맨 발매표 붙여넣기 텍스트 → 승무패(1X2)/머니라인 발매 항목 파서.
//
// 베트맨 화면을 복사하면 게임번호별 블록이 이어진 텍스트가 나온다. 우리 분석은
// "승무패"(축구·하키 3갈래) / "승패"(야구·농구 2갈래) 마켓만 쓰므로, 핸디캡·
// 언더오버·SUM 등 다른 마켓 블록은 건너뛴다.
//
// 인식 규칙(실제 화면 기준):
//   - 마켓 헤더 줄: "축구 승무패", "야구 승5패", "농구 승패" 등 → '승무패'/'승패' 포함
//     ("핸디캡","언더오버","U/O","SUM","소수핸디캡" 포함 줄은 제외)
//   - 선택지 줄: "일본 vs 아이슬란드승  1.14" 형태 (팀 vs 팀 + 승/무/패 + 배당)
//   - "배당률 하락/상승/변동" 등 잡음은 무시

export type Outcome = "home" | "draw" | "away";

export interface ParsedOffering {
  gameNo: string;
  home: string;
  away: string;
  outcome: Outcome;
  odds: number;
}

export interface ParsedMatch {
  gameNo: string;
  home: string;
  away: string;
  hasDraw: boolean;
  offerings: ParsedOffering[];
}

const ODDS_RE = /(\d{1,2}\.\d{1,2})/;
// "팀A vs 팀B<승|무|패>"  뒤에 배당이 같은 줄/다음 토큰에 옴
const PICK_RE = /^(.*?)\s*vs\s*(.+?)(승|무|패)\s*$/i;

// 승무패/승패 마켓 헤더인지 (핸디캡/언오버/SUM 제외)
function isWinDrawLoseHeader(line: string): boolean {
  const l = line.trim();
  if (/핸디캡|언더오버|U\/O|SUM|소수/.test(l)) return false;
  // "축구 승무패", "야구 승패", "농구 승패", "배구 승패" 등
  return /(승무패|승패)\b/.test(l) || /승무패|승패/.test(l);
}

function normalizeTeam(s: string): string {
  return s
    .replace(/\s+/g, " ")
    .replace(/^[|·\-—\s]+|[|·\-—\s]+$/g, "")
    .trim();
}

// 한 줄(또는 인접 줄 결합)에서 선택지+배당을 뽑는다.
// 베트맨 복사본은 "팀 vs 팀승" 과 배당 "1.14" 가 줄바꿈으로 분리되는 경우가 많아,
// 토큰 스트림으로 처리한다.
export function parseBetmanText(raw: string): ParsedMatch[] {
  const lines = raw
    .split("\n")
    .map((l) => l.trim())
    .filter((l) => l.length > 0);

  const matches = new Map<string, ParsedMatch>();
  let curGameNo = "";
  let inWdl = false; // 현재 승무패/승패 마켓 블록 안인가
  let pendingPick: { home: string; away: string; outcome: Outcome } | null =
    null;

  const outcomeMap: Record<string, Outcome> = {
    승: "home",
    무: "draw",
    패: "away",
  };

  for (const line of lines) {
    // 게임번호 (4~5자리 단독 숫자)
    if (/^\d{4,5}$/.test(line)) {
      curGameNo = line;
      inWdl = false;
      pendingPick = null;
      continue;
    }
    // 마켓 헤더
    if (/조합|한경기/.test(line)) continue; // "조합 · 한경기" 무시
    if (/^(축구|야구|농구|배구|아이스하키|하키|이스포츠|e스포츠)/.test(line)) {
      inWdl = isWinDrawLoseHeader(line);
      pendingPick = null;
      continue;
    }
    if (!inWdl) continue;

    // 선택지 줄: "팀 vs 팀<승|무|패>" (+ 같은 줄에 배당이 올 수도)
    const oddsInLine = line.match(ODDS_RE);
    const pickMatch = line.match(PICK_RE);

    if (pickMatch) {
      const home = normalizeTeam(pickMatch[1]);
      const away = normalizeTeam(pickMatch[2]);
      const outcome = outcomeMap[pickMatch[3]];
      // 같은 줄에 배당이 있으면 즉시 확정, 없으면 다음 배당 줄을 기다림
      const odds = line.match(/(승|무|패)\s*(\d{1,2}\.\d{1,2})/);
      if (odds) {
        addOffering(matches, curGameNo, home, away, outcome, parseFloat(odds[2]));
        pendingPick = null;
      } else {
        pendingPick = { home, away, outcome };
      }
      continue;
    }

    // 배당만 있는 줄 → 직전 pending 선택지에 연결
    if (oddsInLine && pendingPick) {
      addOffering(
        matches,
        curGameNo,
        pendingPick.home,
        pendingPick.away,
        pendingPick.outcome,
        parseFloat(oddsInLine[1])
      );
      pendingPick = null;
    }
  }

  return Array.from(matches.values());
}

function addOffering(
  matches: Map<string, ParsedMatch>,
  gameNo: string,
  home: string,
  away: string,
  outcome: Outcome,
  odds: number
) {
  const key = `${gameNo}:${home}:${away}`;
  let m = matches.get(key);
  if (!m) {
    m = { gameNo, home, away, hasDraw: false, offerings: [] };
    matches.set(key, m);
  }
  // 중복 outcome 방지
  if (m.offerings.some((o) => o.outcome === outcome)) return;
  if (outcome === "draw") m.hasDraw = true;
  m.offerings.push({ gameNo, home, away, outcome, odds });
}
