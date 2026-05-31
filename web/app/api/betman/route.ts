import { NextRequest, NextResponse } from "next/server";
import { getServerSupabase } from "@/lib/supabase";
import { ParsedMatch } from "@/lib/betmanParse";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

interface SaveBody {
  round_no: string;
  sport: string;
  matches: ParsedMatch[];
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
// 분석/매칭은 Python run_full_pipeline 이 담당(웹은 입력·저장만).
export async function POST(req: NextRequest) {
  let body: SaveBody;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "잘못된 요청" }, { status: 400 });
  }

  const { round_no, sport, matches } = body;
  if (!round_no || !VALID_SPORTS.has(sport) || !Array.isArray(matches)) {
    return NextResponse.json(
      { error: "round_no / sport / matches 확인" },
      { status: 400 }
    );
  }

  const rows = matches.flatMap((m) =>
    m.offerings.map((o) => ({
      round_no,
      sport,
      home: m.home,
      away: m.away,
      outcome: o.outcome,
      odds: o.odds,
      game_no: m.gameNo,
      sales_open: true,
    }))
  );

  if (rows.length === 0) {
    return NextResponse.json({ error: "저장할 항목 없음" }, { status: 400 });
  }

  try {
    const supabase = getServerSupabase();
    const { error } = await supabase
      .from("betman_manual_odds")
      .upsert(rows, { onConflict: "round_no,sport,home,away,outcome" });
    if (error) {
      return NextResponse.json({ error: error.message }, { status: 500 });
    }
    return NextResponse.json({ saved: rows.length });
  } catch (e: unknown) {
    return NextResponse.json(
      { error: e instanceof Error ? e.message : String(e) },
      { status: 500 }
    );
  }
}
