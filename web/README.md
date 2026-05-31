# Betman Dashboard (Next.js)

Vercel `bet` 프로젝트용 웹 대시보드. Python 분석 레이어가 Supabase `picks`
테이블에 적재한 결과를 읽어 종목별로 value 점수 순으로 표시합니다.

> 분석 로직(de-vig/EV/value/Elo)은 Python 엔진이 담당합니다. 이 앱은 **표시
> 전용**이라 분석 코드를 TypeScript로 중복 구현하지 않습니다.

## 데이터 흐름

```
Python (수집→분석)  →  Supabase: picks 테이블  →  Next.js 대시보드(서버 컴포넌트)
   run_full_pipeline                                getDashboardData()
```

## 로컬 개발

```bash
cd web
cp .env.local.example .env.local     # SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY 채우기
pnpm install        # 또는 npm install
pnpm dev            # http://localhost:3000
```

## Vercel 배포 (`bet` 프로젝트)

1. **Root Directory**: `web` 로 설정 (모노레포이므로 중요).
2. **Environment Variables** 에 추가:
   - `SUPABASE_URL = https://<ref>.supabase.co`
   - `SUPABASE_SERVICE_ROLE_KEY = <service_role_jwt>`
   - ⚠️ `NEXT_PUBLIC_` 접두어를 **붙이지 마세요**. 서버 컴포넌트에서만 읽어
     클라이언트로 키가 노출되지 않습니다.
3. Framework Preset: **Next.js** (자동 감지). Build/Output 기본값 사용.

## 화면

- 환급률 63% 경고 배너 (장기 EV는 구조적 마이너스 — 베팅 권유 아님)
- 축구 / 야구 / 농구 기본 섹션, value 점수 순
- 그 외 종목은 기준선 통과 시 '주목 픽'
- 각 픽: 베트맨 배당 / 공정확률(Pinnacle de-vig) / edge% / EV / value / 근거
- 예산 관리: **한도 없음**(기록만, 경고 비활성) — `lib/data.ts`에서 조정 가능

## 데이터가 안 보일 때

1. `schema.sql` 을 Supabase SQL Editor 에서 실행했는가
2. `python -m scripts.run_full_pipeline` 로 `picks` 를 적재했는가
3. 환경변수(SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY)가 맞는가
