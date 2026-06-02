"use client";

import { useState } from "react";
import { OUTCOME_LABEL, Pick } from "@/lib/types";

function fmtPct(n: number, digits = 1) {
  return `${n >= 0 ? "+" : ""}${n.toFixed(digits)}%`;
}
function won(n: number) {
  return `${Math.round(n).toLocaleString("ko-KR")}원`;
}
function valueClass(v: number): string {
  if (v >= 8) return "value-hi";
  if (v >= 3) return "value-mid";
  if (v >= 0) return "value-lo";
  return "value-neg";
}
function marketLabel(p: Pick): string | null {
  const m = p.market;
  if (m === "match_1x2" || m === "moneyline") return null;
  if (m === "handicap")
    return `핸디캡 ${p.line != null ? (p.line > 0 ? "+" : "") + p.line : ""}`;
  if (m === "totals") return `U/O ${p.line ?? ""}`;
  if (m === "sum") return "SUM";
  return m;
}

export function PickTable({
  picks,
  bankroll,
}: {
  picks: Pick[];
  bankroll: number;
}) {
  const [open, setOpen] = useState<string | null>(null);

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
            <th>value</th>
            <th className="hide-sm">추천 베팅</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {picks.map((p) => {
            const mkt = marketLabel(p);
            const aggWon = (p.kelly_aggressive ?? 0) * bankroll;
            const realWon = (p.kelly_realistic ?? 0) * bankroll;
            const isOpen = open === p.pick_id;
            return (
              <>
                <tr
                  key={p.pick_id}
                  onClick={() => setOpen(isOpen ? null : p.pick_id)}
                  style={{ cursor: "pointer" }}
                >
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
                      {p.model_based ? (
                        <span className="tag model">모델</span>
                      ) : null}
                    </div>
                  </td>
                  <td className="odds">{p.betman_odds.toFixed(2)}</td>
                  <td className="hide-sm muted">
                    {(p.fair_prob * 100).toFixed(1)}%
                  </td>
                  <td>
                    <span className={`delta ${p.edge_pct >= 0 ? "pos" : "neg"}`}>
                      {fmtPct(p.edge_pct)}
                    </span>
                  </td>
                  <td>
                    <span className={`value-badge ${valueClass(p.value_score)}`}>
                      {p.value_score.toFixed(1)}
                    </span>
                  </td>
                  <td className="hide-sm">
                    {aggWon >= 1 ? (
                      <span className="bet-amt">{won(aggWon)}</span>
                    ) : (
                      <span className="muted">비권장</span>
                    )}
                  </td>
                  <td className="muted">{isOpen ? "▲" : "▼"}</td>
                </tr>
                {isOpen ? (
                  <tr key={p.pick_id + "-d"} className="detail-row">
                    <td colSpan={7} className="left">
                      <div className="detail">
                        <p className="explain">{p.explanation}</p>
                        <div className="bet-box">
                          <div>
                            <div className="bet-label">
                              추천 베팅액 (공격적 · 환급률 무시)
                            </div>
                            <div className="bet-val pos">
                              {aggWon >= 1 ? won(aggWon) : "0원 (우위 없음)"}
                            </div>
                            <div className="muted bet-note">
                              해외 공정확률 기준 우위만 본 1/4 켈리. 환급률을
                              빼고 본 ‘이론상 최대’ 금액.
                            </div>
                          </div>
                          <div>
                            <div className="bet-label">
                              현실 베팅액 (환급률 63% 반영)
                            </div>
                            <div className="bet-val">
                              {realWon >= 1 ? won(realWon) : "0원 (비권장)"}
                            </div>
                            <div className="muted bet-note">
                              환급률까지 넣으면 장기 기대값이 마이너스라 대부분
                              0원이 정답입니다.
                            </div>
                          </div>
                        </div>
                        {p.notes && p.notes.length > 0 ? (
                          <p className="muted" style={{ fontSize: 11 }}>
                            {p.notes.join(" · ")}
                          </p>
                        ) : null}
                      </div>
                    </td>
                  </tr>
                ) : null}
              </>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
