import { getDashboardData } from "@/lib/data";
import { SPORT_LABEL } from "@/lib/types";
import { PickTable } from "./PickTable";

// 매 요청마다 최신 데이터를 읽는다 (분석 결과가 자주 바뀜).
export const dynamic = "force-dynamic";

const CORE_ORDER = ["soccer", "baseball", "basketball"];

export default async function Home() {
  const data = await getDashboardData();

  return (
    <main className="container">
      <h1>Betman Value Analyzer</h1>
      <p className="subtitle">
        Pinnacle 기준 공정확률 대비 베트맨 고정배당을 비교해 줄 세운 분석 보조
        {"  "}
        <a href="/betman" style={{ color: "var(--accent)" }}>
          · 베트맨 발매표 입력 →
        </a>
      </p>

      <div className="banner">
        ⚠️ 베트맨 환급률 약 <strong>63%</strong> — 발매되는 모든 픽의 장기
        기대값(EV)은 구조적으로 <strong>마이너스</strong>입니다. 이 화면은 “이기는
        픽”이 아니라 <strong>상대적으로 덜 불리한 픽</strong>을 value 점수로 줄
        세운 것이며, 베팅을 권유하지 않습니다.
      </div>

      {data.error ? (
        <div className="error">
          <strong>데이터를 불러오지 못했습니다.</strong>
          <p style={{ margin: "8px 0 0" }}>
            <code>{data.error}</code>
          </p>
          <p style={{ margin: "8px 0 0" }} className="muted">
            Supabase 환경변수(SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY)를
            확인하고, <code>schema.sql</code> 실행 후{" "}
            <code>python -m scripts.run_full_pipeline</code> 로 picks 를 적재했는지
            확인하세요.
          </p>
        </div>
      ) : null}

      {CORE_ORDER.map((sport) => {
        const picks = data.picksBySport[sport] ?? [];
        return (
          <section className="section" key={sport}>
            <h2>
              {SPORT_LABEL[sport] ?? sport}
              <span className="chip">value 점수 순</span>
              <span className="chip">{picks.length}픽</span>
            </h2>
            <PickTable picks={picks} />
          </section>
        );
      })}

      <section className="section">
        <h2>
          주목 픽
          <span className="chip">비핵심 종목 · 기준선 통과</span>
          <span className="chip">{data.notable.length}픽</span>
        </h2>
        {data.notable.length === 0 ? (
          <div className="empty">기준선을 넘는 비핵심 종목 픽이 없습니다.</div>
        ) : (
          <PickTable picks={data.notable} />
        )}
      </section>

      <div className="footer">
        <p>
          총 {data.totalPicks}픽
          {data.analyzedAt
            ? ` · 분석 시각 ${new Date(data.analyzedAt).toLocaleString("ko-KR")}`
            : ""}{" "}
          · 예산 관리: 한도 없음(기록만)
        </p>
        <p>
          공정확률 = Pinnacle 배당 de-vig(마진 제거). edge = (공정확률 × 배당 −
          1). EV는 환급률 반영. 비정형 신호는 보조 가중치로만 반영됩니다.
        </p>
      </div>
    </main>
  );
}
