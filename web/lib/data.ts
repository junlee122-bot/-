import { getServerSupabase } from "./supabase";
import { Pick } from "./types";

export interface DashboardData {
  picksBySport: Record<string, Pick[]>;
  notable: Pick[];
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
    const supabase = getServerSupabase();
    const { data, error } = await supabase
      .from("picks")
      .select("*")
      .order("value_score", { ascending: false });

    if (error) {
      return {
        picksBySport: {},
        notable: [],
        totalPicks: 0,
        analyzedAt: null,
        error: error.message,
      };
    }

    const picks = (data ?? []) as Pick[];
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

    const analyzedAt =
      picks.length > 0
        ? picks
            .map((p) => p.analyzed_at)
            .sort()
            .slice(-1)[0]
        : null;

    return {
      picksBySport,
      notable,
      totalPicks: picks.length,
      analyzedAt,
      error: null,
    };
  } catch (e: unknown) {
    return {
      picksBySport: {},
      notable: [],
      totalPicks: 0,
      analyzedAt: null,
      error: e instanceof Error ? e.message : String(e),
    };
  }
}
