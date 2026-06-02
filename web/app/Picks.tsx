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
}

// 자금 입력을 들고 있는 클라이언트 래퍼. 입력한 자금에 따라 각 픽의
// 켈리 베팅액(공격적/현실)을 원화로 환산해 보여준다.
export function Picks({ picksBySport, notable }: Props) {
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
