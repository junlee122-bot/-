import { NextRequest, NextResponse } from "next/server";
import { getDb } from "@/lib/firebase";
import { ParsedGame } from "@/lib/betmanParse";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

interface SaveBody {
  round_no: string;
  games: ParsedGame[];
}

// 붙여넣기 파싱 결과를 betman_manual_odds 에 저장. 종목은 게임별로 자동 인식된
// 값을 쓴다. 모든 마켓(승무패/승1패/핸디캡/언오버/SUM)을 저장. 분석/매칭은 Python.
export async function POST(req: NextRequest) {
  let body: SaveBody;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "잘못된 요청" }, { status: 400 });
  }

  const { round_no, games } = body;
  if (!round_no || !Array.isArray(games) || games.length === 0) {
    return NextResponse.json(
      { error: "round_no / games 확인" },
      { status: 400 }
    );
  }

  const rows = games.flatMap((g) =>
    g.offerings.map((o) => ({
      round_no,
      sport: g.sport,
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
    const db = getDb();
    const col = db.collection("betman_manual_odds");

    // 같은 회차를 다시 붙여넣으면 교체(기존 삭제 후 삽입)
    const existing = await col.where("round_no", "==", round_no).get();
    // 삭제 + 삽입을 배치로 (Firestore 배치 한도 500)
    let batch = db.batch();
    let ops = 0;
    const flush = async () => {
      if (ops > 0) {
        await batch.commit();
        batch = db.batch();
        ops = 0;
      }
    };
    for (const doc of existing.docs) {
      batch.delete(doc.ref);
      if (++ops >= 450) await flush();
    }
    for (const row of rows) {
      batch.set(col.doc(), row);
      if (++ops >= 450) await flush();
    }
    await flush();

    return NextResponse.json({ saved: rows.length, games: games.length });
  } catch (e: unknown) {
    return NextResponse.json(
      { error: e instanceof Error ? e.message : String(e) },
      { status: 500 }
    );
  }
}
