"use client";

import { useMemo, useState } from "react";
import { parseBetmanText, ParsedGame } from "@/lib/betmanParse";

const OUTCOME_LABEL: Record<string, string> = {
  home: "승",
  draw: "무",
  away: "패",
  over: "오버",
  under: "언더",
  odd: "홀",
  even: "짝",
};

const SPORT_LABEL: Record<string, string> = {
  soccer: "축구",
  baseball: "야구",
  basketball: "농구",
  volleyball: "배구",
  hockey: "하키",
  esports: "이스포츠",
};

export default function BetmanInput() {
  const [raw, setRaw] = useState("");
  const [round, setRound] = useState("");
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  const games: ParsedGame[] = useMemo(() => {
    if (!raw.trim()) return [];
    try {
      return parseBetmanText(raw);
    } catch {
      return [];
    }
  }, [raw]);

  const totalOfferings = games.reduce((n, g) => n + g.offerings.length, 0);
  const sportCount = useMemo(() => {
    const c: Record<string, number> = {};
    for (const g of games) c[g.sport] = (c[g.sport] ?? 0) + 1;
    return c;
  }, [games]);

  async function save() {
    setMsg(null);
    if (!round.trim()) {
      setMsg({ ok: false, text: "회차를 입력하세요." });
      return;
    }
    if (games.length === 0) {
      setMsg({ ok: false, text: "인식된 게임이 없습니다." });
      return;
    }
    setSaving(true);
    try {
      const res = await fetch("/api/betman", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ round_no: round.trim(), games }),
      });
      const data = await res.json();
      if (!res.ok) {
        setMsg({ ok: false, text: data.error || "저장 실패" });
      } else {
        setMsg({
          ok: true,
          text: `${data.games}게임 / ${data.saved}항목 저장됨. 다음 분석 실행 시 반영됩니다.`,
        });
      }
    } catch (e) {
      setMsg({ ok: false, text: String(e) });
    } finally {
      setSaving(false);
    }
  }

  return (
    <main className="container">
      <p style={{ marginBottom: 8 }}>
        <a href="/" style={{ color: "var(--accent)" }}>
          ← 대시보드로
        </a>
      </p>
      <h1>베트맨 발매표 입력</h1>
      <p className="subtitle">
        베트맨 발매 화면을 통째로 드래그·복사해 붙여넣으세요. <strong>종목(야구/
        축구 등)과 모든 마켓</strong>(승무패·승1패·핸디캡·언더오버·SUM)을 자동으로
        인식합니다. 전반/이닝 등 부분 경기 마켓은 제외됩니다. 핸디캡·언오버·SUM은
        분석 단계에서 Pinnacle → 포아송 모델로 공정확률을 계산해 평가합니다.
      </p>

      <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginBottom: 12 }}>
        <label>
          회차{" "}
          <input
            value={round}
            onChange={(e) => setRound(e.target.value)}
            placeholder="예: 9215 (대표 게임번호 등)"
            style={{ width: 180 }}
          />
        </label>
      </div>

      <textarea
        value={raw}
        onChange={(e) => setRaw(e.target.value)}
        placeholder="여기에 베트맨 발매 화면을 붙여넣으세요…"
        rows={12}
        style={{
          width: "100%",
          background: "var(--panel)",
          color: "var(--text)",
          border: "1px solid var(--border)",
          borderRadius: 8,
          padding: 12,
          fontFamily: "monospace",
          fontSize: 13,
        }}
      />

      <div className="section" style={{ marginTop: 16 }}>
        <h2>
          미리보기
          <span className="chip">{games.length}게임</span>
          <span className="chip">{totalOfferings}항목</span>
          {Object.entries(sportCount).map(([s, c]) => (
            <span className="chip" key={s}>
              {SPORT_LABEL[s] ?? s} {c}
            </span>
          ))}
        </h2>
        {games.length === 0 ? (
          <div className="empty">인식된 마켓이 없습니다.</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th className="left">게임</th>
                <th className="left">종목</th>
                <th className="left">경기</th>
                <th className="left">마켓</th>
                <th className="left">배당</th>
              </tr>
            </thead>
            <tbody>
              {games.map((g) => (
                <tr key={`${g.gameNo}:${g.marketLabel}`}>
                  <td className="left muted">{g.gameNo}</td>
                  <td className="left">{SPORT_LABEL[g.sport] ?? g.sport}</td>
                  <td className="left">
                    {g.home} <span className="muted">vs</span> {g.away}
                  </td>
                  <td className="left">{g.marketLabel}</td>
                  <td className="left">
                    {g.offerings
                      .map(
                        (o) =>
                          `${OUTCOME_LABEL[o.outcome] ?? o.outcome} ${o.odds}`
                      )
                      .join("  ·  ")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {msg ? (
        <div className={msg.ok ? "banner" : "error"} style={{ marginTop: 12 }}>
          {msg.text}
        </div>
      ) : null}

      <button
        onClick={save}
        disabled={saving || games.length === 0}
        style={{
          marginTop: 12,
          padding: "10px 20px",
          background: saving ? "var(--panel-2)" : "var(--accent)",
          color: saving ? "var(--muted)" : "#0b0e14",
          border: "none",
          borderRadius: 8,
          fontWeight: 600,
          cursor: saving || games.length === 0 ? "not-allowed" : "pointer",
        }}
      >
        {saving ? "저장 중…" : `Supabase에 저장 (${totalOfferings}항목)`}
      </button>

      <div className="footer">
        <p>
          같은 회차·종목을 다시 붙여넣으면 기존 입력을 <strong>교체</strong>합니다.
          저장된 배당은 다음 분석 실행(매일 자동 또는 수동 run_full_pipeline,
          <code> BETMAN_SOURCE=supabase</code>) 때 팀명으로 실제 경기와 매칭되어
          edge/EV가 계산됩니다. 핸디캡·언오버·SUM은 모델 기반 추정이라 신뢰도가
          1X2보다 낮게 반영됩니다.
        </p>
      </div>
    </main>
  );
}
