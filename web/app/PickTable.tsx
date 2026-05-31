import { OUTCOME_LABEL, Pick } from "@/lib/types";

function fmtPct(n: number, digits = 1) {
  return `${n >= 0 ? "+" : ""}${n.toFixed(digits)}%`;
}

// value 점수 강도 → 배지 색
function valueClass(v: number): string {
  if (v >= 8) return "value-hi";
  if (v >= 3) return "value-mid";
  if (v >= 0) return "value-lo";
  return "value-neg";
}

// 마켓 + 라인 라벨 (예: 핸디캡 -1.5, U/O 8.5)
function marketLabel(p: Pick): string | null {
  const m = p.market;
  if (m === "match_1x2" || m === "moneyline") return null;
  if (m === "handicap")
    return `핸디캡 ${p.line != null ? (p.line > 0 ? "+" : "") + p.line : ""}`;
  if (m === "totals") return `U/O ${p.line ?? ""}`;
  if (m === "sum") return "SUM";
  return m;
}

export function PickTable({ picks }: { picks: Pick[] }) {
  if (picks.length === 0) {
    return <div className="empty">발매된 픽이 없습니다.</div>;
  }
  return (
    <div className="card">
      <table>
        <thead>
          <tr>
            <th className="left">경기 · 선택</th>
            <th>배당</th>
            <th className="hide-sm">공정%</th>
            <th>edge</th>
            <th className="hide-sm">EV</th>
            <th>value</th>
            <th className="left hide-sm">근거</th>
          </tr>
        </thead>
        <tbody>
          {picks.map((p) => {
            const mkt = marketLabel(p);
            const notes = (p.notes ?? []).filter(
              (n) => !n.startsWith("기준선") && !n.startsWith("모델추정")
            );
            return (
              <tr key={p.pick_id}>
                <td className="left">
                  <div className="match-cell">
                    {p.home_name} <span className="vs">vs</span> {p.away_name}
                    {p.league ? (
                      <span className="league-tag">{p.league}</span>
                    ) : null}
                  </div>
                  <div style={{ marginTop: 4 }}>
                    <span className="outcome">
                      {OUTCOME_LABEL[p.outcome] ?? p.outcome}
                    </span>
                    {mkt ? <span className="tag">{mkt}</span> : null}
                  </div>
                </td>
                <td className="odds">{p.betman_odds.toFixed(2)}</td>
                <td className="hide-sm muted">{(p.fair_prob * 100).toFixed(1)}%</td>
                <td>
                  <span
                    className={`delta ${p.edge_pct >= 0 ? "pos" : "neg"}`}
                  >
                    {fmtPct(p.edge_pct)}
                  </span>
                </td>
                <td className={`hide-sm ${p.expected_value >= 0 ? "pos" : "neg"}`}>
                  {p.expected_value.toFixed(2)}
                </td>
                <td>
                  <span className={`value-badge ${valueClass(p.value_score)}`}>
                    {p.value_score.toFixed(1)}
                  </span>
                </td>
                <td className="left hide-sm">
                  {p.model_based ? <span className="tag model">모델</span> : null}
                  {p.mean_reversion ? (
                    <span className="tag mr">평균회귀</span>
                  ) : null}
                  {p.signals && p.signals.length > 0 ? (
                    <span className="tag">신호 {p.signals.length}</span>
                  ) : null}
                  {notes.length > 0 ? (
                    <span className="note-text">{notes.join(" · ")}</span>
                  ) : null}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
