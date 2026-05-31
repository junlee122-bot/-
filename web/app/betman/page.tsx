"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { parseBetmanText, ParsedMatch } from "@/lib/betmanParse";

const SPORTS = [
  { key: "soccer", label: "축구" },
  { key: "baseball", label: "야구" },
  { key: "basketball", label: "농구" },
  { key: "volleyball", label: "배구" },
  { key: "hockey", label: "하키" },
  { key: "esports", label: "이스포츠" },
];

const OUTCOME_LABEL: Record<string, string> = {
  home: "승",
  draw: "무",
  away: "패",
};

export default function BetmanInput() {
  const [raw, setRaw] = useState("");
  const [sport, setSport] = useState("soccer");
  const [round, setRound] = useState("");
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  const matches: ParsedMatch[] = useMemo(() => {
    if (!raw.trim()) return [];
    try {
      return parseBetmanText(raw);
    } catch {
      return [];
    }
  }, [raw]);

  const totalOfferings = matches.reduce((n, m) => n + m.offerings.length, 0);

  async function save() {
    setMsg(null);
    if (!round.trim()) {
      setMsg({ ok: false, text: "회차를 입력하세요." });
      return;
    }
    if (matches.length === 0) {
      setMsg({ ok: false, text: "인식된 경기가 없습니다." });
      return;
    }
    setSaving(true);
    try {
      const res = await fetch("/api/betman", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ round_no: round.trim(), sport, matches }),
      });
      const data = await res.json();
      if (!res.ok) {
        setMsg({ ok: false, text: data.error || "저장 실패" });
      } else {
        setMsg({
          ok: true,
          text: `${data.saved}개 항목 저장됨. 다음 분석 실행 시 반영됩니다.`,
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
        <Link href="/" style={{ color: "var(--accent)" }}>
          ← 대시보드로
        </Link>
      </p>
      <h1>베트맨 발매표 입력</h1>
      <p className="subtitle">
        베트맨 발매 화면을 드래그·복사해 붙여넣으면 <strong>승무패/승패</strong>{" "}
        배당만 자동 추출합니다 (핸디캡·언오버·SUM은 제외).
      </p>

      <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginBottom: 12 }}>
        <label>
          종목{" "}
          <select value={sport} onChange={(e) => setSport(e.target.value)}>
            {SPORTS.map((s) => (
              <option key={s.key} value={s.key}>
                {s.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          회차{" "}
          <input
            value={round}
            onChange={(e) => setRound(e.target.value)}
            placeholder="예: 8994"
            style={{ width: 100 }}
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
          <span className="chip">{matches.length}경기</span>
          <span className="chip">{totalOfferings}항목</span>
        </h2>
        {matches.length === 0 ? (
          <div className="empty">
            승무패/승패 마켓이 인식되지 않았습니다. (핸디캡·언오버는 자동 제외)
          </div>
        ) : (
          <table>
            <thead>
              <tr>
                <th className="left">게임번호</th>
                <th className="left">경기</th>
                <th className="left">승</th>
                <th className="left">무</th>
                <th className="left">패</th>
              </tr>
            </thead>
            <tbody>
              {matches.map((m) => {
                const byOc = Object.fromEntries(
                  m.offerings.map((o) => [o.outcome, o.odds])
                );
                return (
                  <tr key={`${m.gameNo}:${m.home}:${m.away}`}>
                    <td className="left muted">{m.gameNo}</td>
                    <td className="left">
                      {m.home} <span className="muted">vs</span> {m.away}
                    </td>
                    <td className="left">{byOc.home ?? "-"}</td>
                    <td className="left">{byOc.draw ?? "-"}</td>
                    <td className="left">{byOc.away ?? "-"}</td>
                  </tr>
                );
              })}
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
        disabled={saving || matches.length === 0}
        style={{
          marginTop: 12,
          padding: "10px 20px",
          background: saving ? "var(--panel-2)" : "var(--accent)",
          color: saving ? "var(--muted)" : "#0b0e14",
          border: "none",
          borderRadius: 8,
          fontWeight: 600,
          cursor: saving || matches.length === 0 ? "not-allowed" : "pointer",
        }}
      >
        {saving ? "저장 중…" : `Supabase에 저장 (${totalOfferings}항목)`}
      </button>

      <div className="footer">
        <p>
          저장된 배당은 다음 분석 실행(매일 자동 또는 수동 run_full_pipeline) 때
          팀명으로 실제 경기와 매칭되어 edge/EV가 계산됩니다. 한글 팀명이 영문과
          매칭되도록 <code>data/betman/aliases.json</code> 을 관리하세요.
        </p>
      </div>
    </main>
  );
}
