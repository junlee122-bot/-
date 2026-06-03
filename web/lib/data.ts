import { getDb } from "./firebase";
import { Pick } from "./types";

export interface DashboardData {
  picksBySport: Record<string, Pick[]>;
  notable: Pick[];
  topPicks: Pick[]; // 오늘의 추천(신뢰도 높은 순 상위)
  totalPicks: number;
  analyzedAt: string | null;
  error: string | null;
}

const CORE = ["soccer", "baseball", "basketball"];

// 종목별 '주목 픽' 기준선 (Python value.py 캘리브레이션과 일치)
const NOTABLE_THRESHOLD: Record<string, number> = {
  volleyball: 8.0,
  hockey: 8.0,
  esports: 8.0,
};

export async function getDashboardData(): Promise<DashboardData> {
  try {
    const db = getDb();
    const snap = await db
      .collection("picks")
      .orderBy("value_score", "desc")
      .get();

    const allPicks = snap.docs.map((d) => d.data() as Pick);

    // 가장 최근 분석 배치만 표시 (이전 회차/분석 결과는 숨김).
    const latest = allPicks
      .map((p) => p.analyzed_at)
      .filter(Boolean)
      .sort()
      .slice(-1)[0];
    const picks = latest
      ? allPicks.filter((p) => p.analyzed_at === latest)
      : allPicks;

    const picksBySport: Record<string, Pick[]> = {};
    const notable: Pick[] = [];

    for (const p of picks) {
      if (CORE.includes(p.sport)) {
        (picksBySport[p.sport] ??= []).push(p);
      } else {
        const threshold = NOTABLE_THRESHOLD[p.sport] ?? 8.0;
        if (p.value_score >= threshold) notable.push(p);
      }
    }

    const analyzedAt = latest ?? null;

    // 오늘의 추천: 신뢰도 높은(모델 추정 아닌) edge>0 픽을 value 순 상위 5개.
    // 모델 추정뿐이면 그중에서라도 상위를 보여준다(경고와 함께).
    const positive = picks.filter((p) => p.edge_pct > 0);
    const reliable = positive.filter((p) => !p.model_based);
    const pool = reliable.length > 0 ? reliable : positive;
    const topPicks = [...pool]
      .sort((a, b) => b.value_score - a.value_score)
      .slice(0, 5);

    return {
      picksBySport,
      notable,
      topPicks,
      totalPicks: picks.length,
      analyzedAt,
      error: null,
    };
  } catch (e: unknown) {
    return {
      picksBySport: {},
      notable: [],
      topPicks: [],
      totalPicks: 0,
      analyzedAt: null,
      error: e instanceof Error ? e.message : String(e),
    };
  }
}
