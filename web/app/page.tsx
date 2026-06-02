import { getDashboardData } from "@/lib/data";
import { Picks } from "./Picks";

// 매 요청마다 최신 데이터를 읽는다 (분석 결과가 자주 바뀜).
export const dynamic = "force-dynamic";

export default async function Home() {
  const data = await getDashboardData();

  // 요약 통계
  const allPicks = [
    ...Object.values(data.picksBySport).flat(),
    ...data.notable,
  ];
  const positiveEdge = allPicks.filter((p) => p.edge_pct > 0).length;
  const bestValue =
    allPicks.length > 0
      ? Math.max(...allPicks.map((p) => p.value_score))
      : null;

  return (
    <main className="container">
      <header className="app-header">
        <div className="brand">
          <div className="brand-mark">📊</div>
          <div>
            <h1>Betman Value Analyzer</h1>
            <p className="subtitle">
              Pinnacle 공정확률 대비 베트맨 배당을 value 점수로 줄세우기
            </p>
          </div>
        </div>
        <a href="/betman" className="cta">
          ✏️ 발매표 입력
        </a>
      </header>

      <div className="banner">
        <span className="ico">⚠️</span>
        <span>
          베트맨 환급률 약 <strong>63%</strong> — 모든 픽의 장기 기대값(EV)은
          구조적으로 <strong>마이너스</strong>입니다. 이 화면은 “이기는 픽”이
          아니라 <strong>상대적으로 덜 불리한 픽</strong>을 줄 세운 분석 보조이며,
          베팅을 권유하지 않습니다.
        </span>
      </div>

      {data.error ? (
        <div className="error">
          <strong>데이터를 불러오지 못했습니다.</strong>
          <p style={{ margin: "8px 0 0" }}>
            <code>{data.error}</code>
          </p>
          <p style={{ margin: "8px 0 0" }} className="muted">
            환경변수(SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY) 및{" "}
            <code>run_full_pipeline</code> 실행 여부를 확인하세요.
          </p>
        </div>
      ) : null}

      {/* 요약 통계 */}
      <div className="stats">
        <div className="stat-card">
          <div className="stat-label">총 분석 픽</div>
          <div className="stat-value">{data.totalPicks}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">+edge 픽</div>
          <div className="stat-value">{positiveEdge}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">최고 value</div>
          <div className="stat-value">
            {bestValue !== null ? bestValue.toFixed(1) : "–"}
          </div>
        </div>
        <div className="stat-card">
          <div className="stat-label">마지막 분석</div>
          <div className="stat-value" style={{ fontSize: 14, paddingTop: 6 }}>
            {data.analyzedAt
              ? new Date(data.analyzedAt).toLocaleString("ko-KR", {
                  month: "numeric",
                  day: "numeric",
                  hour: "2-digit",
                  minute: "2-digit",
                })
              : "–"}
          </div>
        </div>
      </div>

      <Picks picksBySport={data.picksBySport} notable={data.notable} />

      <div className="banner" style={{ marginTop: 8 }}>
        <span className="ico">💡</span>
        <span>
          각 픽을 <strong>클릭</strong>하면 쉬운 말 설명과 추천 베팅액(공격적 ·
          현실)이 펼쳐집니다. <strong>공격적</strong>은 환급률을 뺀 이론상 최대,
          <strong> 현실</strong>은 환급률 63%까지 반영한 금액(대부분 0원)입니다.
        </span>
      </div>

      <div className="footer">
        <p>
          <strong>공정확률</strong> = Pinnacle 배당 de-vig(마진 제거) ·{" "}
          <strong>edge</strong> = 공정확률 × 배당 − 1 · <strong>EV</strong>는
          환급률 반영 · <span className="tag model">모델</span>은 포아송 추정(신뢰도↓)
        </p>
        <p>예산 관리: 한도 없음(기록만) · 비정형 신호는 보조 가중치로만 반영됩니다.</p>
      </div>
    </main>
  );
}
