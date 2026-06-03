"use client";

import { useState } from "react";
import { Pick, SPORT_LABEL } from "@/lib/types";
import { PickTable } from "./PickTable";

const CORE = [
  { key: "soccer", icon: "⚽" },
  { key: "baseball", icon: "⚾" },
  { key: "basketball", icon: "🏀" },
];

interface Props {
  picksBySport: Record<string, Pick[]>;
  notable: Pick[];
  topPicks: Pick[];
}

const OUTCOME_LABEL: Record<string, string> = {
  home: "홈 승",
  draw: "무",
  away: "원정 승",
  over: "오버",
  under: "언더",
  odd: "홀",
  even: "짝",
};
const MARKET_LABEL: Record<string, string> = {
  match_1x2: "승무패",
  moneyline: "승패",
  handicap: "핸디캡",
  totals: "언더오버",
  sum: "홀짝",
};

function won(n: number) {
  return `${Math.round(n).toLocaleString("ko-KR")}원`;
}

// 자금 입력을 들고 있는 클라이언트 래퍼. 입력한 자금에 따라 각 픽의
// 켈리 베팅액(공격적/현실)을 원화로 환산해 보여준다.
export function Picks({ picksBySport, notable, topPicks }: Props) {
  const [bankrollMan, setBankrollMan] = useState(10); // 만원 단위
  const bankroll = bankrollMan * 10000;

  return (
    <>
      <div className="bankroll">
        <label>
          💰 내 자금
          <input
            type="number"
            min={0}
            step={1}
            value={bankrollMan}
            onChange={(e) => setBankrollMan(Math.max(0, Number(e.target.value)))}
            style={{ width: 90, marginLeft: 8 }}
          />
          만원
        </label>
        <span className="muted" style={{ fontSize: 12 }}>
          입력한 자금 기준으로 각 픽의 추천 베팅액을 계산합니다.
        </span>
      </div>

      {/* 오늘의 추천 — 무엇을 어떻게 고를지 직관적으로 */}
      <section className="section">
        <div className="section-head">
          <span className="section-icon">🎯</span>
          <h2>오늘의 추천 — 이렇게 고르세요</h2>
        </div>
        {topPicks.length === 0 ? (
          <div className="empty">
            지금은 ‘해외 기준보다 후한’ 픽이 없습니다. 이런 날은 <strong>쉬는 게
            이득</strong>입니다.
          </div>
        ) : (
          <div className="guide">
            <p className="guide-lead">
              아래는 지금 발매된 것 중 <strong>해외 시장 대비 그나마 가장 덜
              불리한</strong> 순서입니다. 위에서부터 골라보세요.
              {topPicks.some((p) => p.model_based) ? (
                <span className="muted">
                  {" "}
                  (⚠️ 표시는 추정값이라 신뢰도 낮음)
                </span>
              ) : null}
            </p>
            <ol className="guide-list">
              {topPicks.map((p, i) => {
                const mk = MARKET_LABEL[p.market] ?? p.market;
                const oc = OUTCOME_LABEL[p.outcome] ?? p.outcome;
                const lineTxt =
                  p.line != null
                    ? p.market === "handicap"
                      ? ` ${p.line > 0 ? "+" : ""}${p.line}`
                      : ` ${p.line}`
                    : "";
                const agg = (p.kelly_aggressive ?? 0) * bankroll;
                return (
                  <li key={p.pick_id} className="guide-item">
                    <div className="guide-rank">{i + 1}</div>
                    <div className="guide-body">
                      <div className="guide-title">
                        {p.home_name} <span className="muted">vs</span>{" "}
                        {p.away_name}
                        {p.model_based ? (
                          <span className="tag model">⚠️ 추정</span>
                        ) : null}
                      </div>
                      <div className="guide-pick">
                        👉 <strong>{mk}{lineTxt}</strong> 에서{" "}
                        <strong className="hl">{oc}</strong> 에 베팅 · 배당{" "}
                        {p.betman_odds.toFixed(2)}
                      </div>
                      <div className="guide-meta">
                        해외기준 <span className="pos">{p.edge_pct >= 0 ? "+" : ""}
                        {p.edge_pct.toFixed(0)}% 후함</span> · 추천액{" "}
                        {agg >= 1 ? (
                          <strong>{won(agg)}</strong>
                        ) : (
                          <span className="muted">소액/비권장</span>
                        )}
                      </div>
                    </div>
                  </li>
                );
              })}
            </ol>
            <p className="guide-foot muted">
              ‘추천액’은 자금({bankrollMan}만원)에서 수수료를 무시했을 때의 이론상
              금액입니다. 실제로는 베트맨 수수료(37%) 때문에 길게 보면 손해라,
              <strong> 즐기는 선</strong>에서만 거세요. 각 픽을 누르면 자세한 설명이
              나옵니다.
            </p>
          </div>
        )}
      </section>

      {CORE.map(({ key, icon }) => {
        const picks = picksBySport[key] ?? [];
        return (
          <section className="section" key={key}>
            <div className="section-head">
              <span className="section-icon">{icon}</span>
              <h2>{SPORT_LABEL[key] ?? key}</h2>
              <span className="chip">value 순</span>
              <span className="chip">{picks.length}픽</span>
            </div>
            <PickTable picks={picks} bankroll={bankroll} />
          </section>
        );
      })}

      <section className="section">
        <div className="section-head">
          <span className="section-icon">⭐</span>
          <h2>주목 픽</h2>
          <span className="chip">비핵심 종목 · 기준선 통과</span>
          <span className="chip">{notable.length}픽</span>
        </div>
        {notable.length === 0 ? (
          <div className="empty">기준선을 넘는 비핵심 종목 픽이 없습니다.</div>
        ) : (
          <PickTable picks={notable} bankroll={bankroll} />
        )}
      </section>
    </>
  );
}
