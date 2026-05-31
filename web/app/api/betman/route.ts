import { NextRequest, NextResponse } from "next/server";
import { getServerSupabase } from "@/lib/supabase";
import { ParsedGame } from "@/lib/betmanParse";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

interface SaveBody {
  round_no: string;
  sport: string;
  games: ParsedGame[];
}

const VALID_SPORTS = new Set([
  "soccer",
  "baseball",
  "basketball",
  "volleyball",
  "hockey",
  "esports",
]);

// 붙여넣기 파싱 결과를 betman_manual_odds 에 upsert 저장.
// 모든 마켓(승무패/핸디캡/언오버/SUM)을 저장한다. 분석/매칭은 Python.
export async function POST(req: NextRequest) {
  let body: SaveBody;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "잘못된 요청" }, { status: 400 });
  }

  const { round_no, sport, games } = body;
  if (!round_no || !VALID_SPORTS.has(sport) || !Array.isArray(games)) {
    return NextResponse.json(
      { error: "round_no / sport / games 확인" },
      { status: 400 }
    );
  }

  const rows = games.flatMap((g) =>
    g.offerings.map((o) => ({
      round_no,
      sport,
      home: g.home,
      away: g.away,
      market: g.market,
      line: g.line,
      outcome: o.outcome,
      odds: o.odds,
      game_no: g.gameNo,
      sales_open: true,
    }))
  );

  if (rows.length === 0) {
    return NextResponse.json({ error: "저장할 항목 없음" }, { status: 400 });
  }

  try {
    const supabase = getServerSupabase();
    // 같은 회차·종목을 다시 붙여넣으면 교체(기존 삭제 후 삽입)
    const del = await supabase
      .from("betman_manual_odds")
      .delete()
      .eq("round_no", round_no)
      .eq("sport", sport);
    if (del.error) {
      return NextResponse.json({ error: del.error.message }, { status: 500 });
    }
    const { error } = await supabase.from("betman_manual_odds").insert(rows);
    if (error) {
      return NextResponse.json({ error: error.message }, { status: 500 });
    }
    return NextResponse.json({ saved: rows.length, games: games.length });
  } catch (e: unknown) {
    return NextResponse.json(
      { error: e instanceof Error ? e.message : String(e) },
      { status: 500 }
    );
  }
}
