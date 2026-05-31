import { OUTCOME_LABEL, Pick } from "@/lib/types";

function fmtPct(n: number, digits = 1) {
  return `${n.toFixed(digits)}%`;
}

function evClass(n: number) {
  return n >= 0 ? "pos" : "neg";
}

export function PickTable({ picks }: { picks: Pick[] }) {
  if (picks.length === 0) {
    return <div className="empty">발매된 픽이 없습니다.</div>;
  }
  return (
    <table>
      <thead>
        <tr>
          <th className="left">경기</th>
          <th className="left">선택</th>
          <th>베트맨 배당</th>
          <th>공정확률</th>
          <th>edge</th>
          <th>EV</th>
          <th>value</th>
          <th className="left">근거</th>
        </tr>
      </thead>
      <tbody>
        {picks.map((p) => (
          <tr key={p.pick_id}>
            <td className="left">
              {p.home_name} <span className="muted">vs</span> {p.away_name}
              {p.league ? <span className="tag">{p.league}</span> : null}
            </td>
            <td className="left">{OUTCOME_LABEL[p.outcome] ?? p.outcome}</td>
            <td>{p.betman_odds.toFixed(2)}</td>
            <td>{fmtPct(p.fair_prob * 100)}</td>
            <td className={evClass(p.edge_pct)}>{fmtPct(p.edge_pct)}</td>
            <td className={evClass(p.expected_value)}>
              {p.expected_value.toFixed(2)}
            </td>
            <td>{p.value_score.toFixed(2)}</td>
            <td className="left muted">
              {p.mean_reversion ? <span className="tag mr">평균회귀</span> : null}
              {p.signals && p.signals.length > 0 ? (
                <span className="tag">신호 {p.signals.length}</span>
              ) : null}
              {p.notes && p.notes.length > 0 ? (
                <span> {p.notes.filter((n) => !n.startsWith("기준선")).join(" · ")}</span>
              ) : null}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
